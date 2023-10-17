import os
import re
import datetime
import hashlib
import logging
from datetime import datetime
from mcrit.client.McritClient import McritClient
from mcrit.storage.MatchingResult import MatchingResult
from mcrit.storage.MatchedFunctionEntry import MatchedFunctionEntry
from mcrit.storage.FunctionEntry import FunctionEntry
from mcrit.storage.SampleEntry import SampleEntry
from mcrit.queue.LocalQueue import Job
from flask import current_app, Blueprint, render_template, request, redirect, url_for, Response, flash, session, send_from_directory, json

from mcritweb.db import get_user_result_filters
from mcritweb.views.analyze import query as analyze_query
from mcritweb.views.utility import get_server_url, get_username, mcrit_server_required, parseBitnessFromFilename, parseBaseAddrFromFilename, get_matches_node_colors, parse_integer_query_param, parse_integer_list_query_param, parse_checkbox_query_param, parse_str_query_param, get_session_user_id
from mcritweb.views.pagination import Pagination
from mcritweb.views.cross_compare import get_sample_to_job_id, score_to_color
from mcritweb.views.authentication import visitor_required, contributor_required
from mcritweb.views.ScoreColorProvider import ScoreColorProvider
from mcritweb.views.MatchReportRenderer import MatchReportRenderer

bp = Blueprint('data', __name__, url_prefix='/data')

################################################################
# Helper functions
################################################################

def load_cached_result(app, job_id):
    matching_result = {}
    cache_path = os.sep.join([app.instance_path, "cache", "results"])
    for filename in os.listdir(cache_path):
        if job_id in filename and filename.endswith("json"):
            with open(cache_path + os.sep + filename, "r") as fin:
                matching_result = json.load(fin)
    return matching_result


def cache_result(app, job_info, matching_result):
    # TODO potentially implement a cache control that manages maximum allowed cache size?
    if job_info.result is not None:
        cache_path = os.sep.join([app.instance_path, "cache", "results"])
        timestamped_filename = datetime.utcnow().strftime(f"%Y%m%d-%H%M%S-{job_info.job_id}.json")
        with open(cache_path + os.sep + timestamped_filename, "w") as fout:
            json.dump(matching_result, fout, indent=1)


def create_match_diagram(app, job_id, matching_result, filtered_family_id=None, filtered_sample_id=None, filtered_function_id=None):
    cache_path = os.sep.join([app.instance_path, "cache", "diagrams"])
    filter_suffix = ""
    if filtered_family_id is not None:
        filter_suffix = f"-famid_{filtered_family_id}"
    elif filtered_sample_id is not None:
        filter_suffix = f"-samid_{filtered_sample_id}"
    elif filtered_function_id is not None:
        filter_suffix = f"-funid_{filtered_function_id}"
    output_path = cache_path + os.sep + job_id + filter_suffix + ".png"
    if not os.path.isfile(output_path):
        renderer = MatchReportRenderer()
        renderer.processReport(matching_result)
        image = renderer.renderStackedDiagram(filtered_family_id=filtered_family_id, filtered_sample_id=filtered_sample_id, filtered_function_id=filtered_function_id)
        image.save(output_path)
        print("stored new MCRIT diagram:", output_path)

# https://stackoverflow.com/a/39842765
# https://stackoverflow.com/a/26972238
# https://flask.palletsprojects.com/en/1.0.x/api/#flask.send_from_directory
@bp.route('/diagrams/<path:filename>')
def diagram_file(filename):
    cache_path = os.sep.join([current_app.instance_path, "cache", "diagrams"])
    return send_from_directory(cache_path, filename)


################################################################
# Import + Export
################################################################

@bp.route('/import',methods=('GET', 'POST'))
@mcrit_server_required
@contributor_required
def import_view():
    if request.method == 'POST':
        f = request.files.get('file', '')
        client = McritClient(mcrit_server=get_server_url(), username=get_username())
        session["last_import"] = client.addImportData(json.load(f))
    return render_template("import.html")

@bp.route('/import_complete')
@contributor_required
def import_complete():
    import_results = session.pop('last_import',{})
    if import_results:
        return render_template("import_complete.html", results=import_results)
    else:
        flash("This doesn't seem to be valid MCRIT data in JSON format", category='error')
        return render_template("import.html")


@bp.route('/export',methods=('GET', 'POST'))
@mcrit_server_required
@contributor_required
def export_view():
    if request.method == 'POST':
        requested_samples = request.form['samples']
        client = McritClient(mcrit_server=get_server_url(), username=get_username())
        if requested_samples == "":
            export_file = json.dumps(client.getExportData())
            return Response(
                export_file,
                mimetype='application/json',
                headers={"Content-disposition":
                        "attachment; filename=export_all_samples.json"})
        # NOTE it might be nice to allow [<number>, <number>-<number>, ...] to enable 
        # spans of consecutive sample_ids
        elif re.match("^\d+(?:[\s]*,[\s]*\d+)*$", requested_samples):
            sample_ids = [int(sample_id.strip()) for sample_id in requested_samples.split(',')]
            export_file = json.dumps(client.getExportData(sample_ids))
            return Response(
                export_file,
                mimetype='application/json',
                headers={"Content-disposition":
                        "attachment; filename=export_samples.json"})
        else:
            flash('Please use a comma-separated list of sample_ids in your export request.', category='error')
            return render_template("export.html")
    return render_template("export.html")

@bp.route('/specific_export/<type>/<item_id>')
@mcrit_server_required
@contributor_required
def specific_export(type, item_id):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    if type == 'family':
        samples = client.getSamplesByFamilyId(item_id)
        sample_ids = [x.sample_id for x in samples.values()]
        export_file = json.dumps(client.getExportData(sample_ids))
        return Response(
            export_file,
            mimetype='application/json',
            headers={"Content-disposition":
                    "attachment; filename=export_family_"+str(item_id)+".json"})
    if type == 'samples':
        sample_ids = []
        sample_entry = client.getSampleById(item_id)
        if sample_entry:
            sample_ids.append(sample_entry.sample_id)
        export_file = json.dumps(client.getExportData(sample_ids))
        return Response(
            export_file,
            mimetype='application/json',
            headers={"Content-disposition":
                    "attachment; filename=export_samples.json"})

################################################################
# Direct Function Matching
################################################################

@bp.route('/matches/function/<function_id_a>/<function_id_b>')
@mcrit_server_required
@visitor_required
def match_functions(function_id_a, function_id_b):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    if client.isFunctionId(function_id_a) and client.isFunctionId(function_id_b):
        match_info = client.getMatchFunctionVs(function_id_a, function_id_b)
        function_entry = FunctionEntry.fromDict(match_info["function_entry_a"])
        pichash_matches_a = client.getMatchesForPicHash(function_entry.pichash, summary=True)
        sample_entry_a = SampleEntry.fromDict(match_info["sample_entry_a"])
        other_function_entry = FunctionEntry.fromDict(match_info["function_entry_b"])
        sample_entry_b = SampleEntry.fromDict(match_info["sample_entry_b"])
        pichash_matches_b = client.getMatchesForPicHash(other_function_entry.pichash, summary=True)
        matched_function_entry = MatchedFunctionEntry(match_info["match_entry"]["fid"], match_info["match_entry"]["num_bytes"], match_info["match_entry"]["offset"], match_info["match_entry"]["matches"])
        node_colors = get_matches_node_colors(function_id_a, function_id_b)
        return render_template(
            "result_compare_function_vs.html",
            entry_a=function_entry,
            entry_b=other_function_entry,
            sample_entry_a=sample_entry_a,
            sample_entry_b=sample_entry_b,
            pichash_matches_a=pichash_matches_a,
            pichash_matches_b=pichash_matches_b,
            match_result=matched_function_entry,
            node_colors=json.dumps(node_colors)
        )
    flash("One of the function_ids is not valid.", category='error')
    return render_template("index.html")

################################################################
# Result presentation
################################################################

@bp.route('/result/<job_id>')
@mcrit_server_required
@visitor_required
# TODO:  refactor, simplify
def result(job_id):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    # check if we have the respective report already locally cached
    result_json = load_cached_result(current_app, job_id)
    job_info = client.getJobData(job_id)
    if not result_json:
        # otherwise obtain result report from remote
            result_json = client.getResultForJob(job_id)
            if result_json:
                cache_result(current_app, job_info, result_json)
    if result_json:
        score_color_provider = ScoreColorProvider()
        # TODO validation - only parse to matching_result if this data type is appropriate 
        # re-format result report for visualization and choose respective template
        if job_info is None:
            return render_template("result_invalid.html", job_id=job_id)
        if job_info.parameters.startswith("getMatchesForSampleVs"):
            matching_result = MatchingResult.fromDict(result_json)
            return result_matches_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForSample"):
            matching_result = MatchingResult.fromDict(result_json)
            return result_matches_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForSmdaReport"):
            matching_result = MatchingResult.fromDict(result_json)
            return result_matches_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForMappedBinary"):
            matching_result = MatchingResult.fromDict(result_json)
            return result_matches_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForUnmappedBinary"):
            matching_result = MatchingResult.fromDict(result_json)
            return result_matches_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("combineMatchesToCross"):
            return result_matches_for_cross(job_info, result_json)
        # NOTE: 'updateMinHashes' is the start of 'updateMinHashesForSample'.
        # For this reason, these two elif clauses should not be reordered
        elif job_info.parameters.startswith("updateMinHashesForSample"):
            return render_template("result_empty.html", job_id=job_id)
        elif job_info.parameters.startswith("updateMinHashes"):
            return render_template("result_empty.html", job_id=job_id)
        elif job_info.parameters.startswith("getUniqueBlocks"):
            return result_unique_blocks(job_info, result_json)
        elif job_info.parameters.startswith("addBinarySample"):
            return redirect(url_for('explore.sample_by_id', sample_id=result_json['sample_info']['sample_id']))
        # modify and delete samples and families
        elif job_info.parameters.startswith("deleteSample"):
            return redirect(url_for('explore.samples'))
        elif job_info.parameters.startswith("modifySample"):
            return redirect(url_for('explore.samples'))
        elif job_info.parameters.startswith("deleteFamily"):
            return redirect(url_for('explore.families'))
        elif job_info.parameters.startswith("modifyFamily"):
            return redirect(url_for('explore.families'))
    elif job_info:
        # if we are not done processing, list job data
        return render_template("job_in_progress.html", job_info=job_info)
    else:
        # if we can't find job or result, we have to assume the job_id was invalid
        return render_template("result_invalid.html", job_id=job_id)

def build_yara_rule(job_info, blocks_result, blocks_statistics):
    unique_blocks = blocks_result["unique_blocks"]
    yara_blocks = blocks_result["yara_rule"]
    yara_rule = f"rule mcrit_{job_info.job_id} {{\n"
    yara_rule += "    meta:\n"
    yara_rule += "        author = \"MCRIT YARA Generator\"\n"
    yara_rule += f"        description = \"Code-based YARA rule composed from potentially unique basic blocks for the selected set of samples/family.\"\n"
    rule_date = datetime.utcnow().strftime("%Y-%m-%d")
    yara_rule += f"        date = \"{rule_date}\"\n"
    yara_rule += "    strings:\n"
    yara_rule += f"        // Rule generation selected {len(yara_blocks)} picblocks, covering {blocks_statistics['num_samples_covered']}/{blocks_statistics['num_samples']} input sample(s).\n"
    for pichash, result in unique_blocks.items():
        if pichash not in yara_blocks:
            continue
        yarafied = f"        /* picblockhash: {pichash} - coverage: {len(result['samples'])}/{blocks_statistics['num_samples_covered']} samples.\n"
        maxlen_ins = max([len(ins[1]) for ins in result["instructions"]])
        for ins in result["instructions"]:
            yarafied += f"         * {ins[1]:{maxlen_ins}} | {ins[2]} {ins[3]}\n"
        yarafied += "         */\n"
        yarafied += f"        $blockhash_{pichash} = {{ " + re.sub("(.{80})", "\\1\n", result["escaped_sequence"], 0, re.DOTALL) + " }\n"
        yara_rule += yarafied + "\n"
    yara_rule += "    condition:\n"
    yara_rule += "        7 of them\n"
    yara_rule += "}"
    return yara_rule

def result_unique_blocks(job_info, blocks_result: dict):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    payload_params = json.loads(job_info.payload["params"])
    sample_ids = payload_params["0"]
    sample_id = sample_ids[0]
    family_id = None
    family_entry = None
    if "family_id" in payload_params:
        family_id = payload_params["family_id"]
        family_entry = client.getFamily(family_id)
    if blocks_result is None:
        if family_id is not None:
            flash(f"No results for unique blocks in family with id {family_id}", category="error")
        else:
            flash(f"No results for unique blocks in family with id {sample_id}", category="error")
    blocks_statistics = blocks_result["statistics"]
    yara_rule = build_yara_rule(job_info, blocks_result, blocks_statistics)
    unique_blocks = blocks_result["unique_blocks"]

    paginated_blocks = []
    # TODO this result object has changed, we should split it into stats/blocks/yara and process further
    if unique_blocks is not None:
        min_score = parse_integer_query_param(request, "min_score")
        min_block_length = parse_integer_query_param(request, "min_block_length")
        max_block_length = parse_integer_query_param(request, "max_block_length")
        active_tab = request.args.get('tab','stats')
        active_tab = active_tab if active_tab in ["stats", "yara", "blocks"] else "stats"
        filtered_blocks = unique_blocks
        if min_score:
            filtered_blocks = {pichash: block for pichash, block in unique_blocks.items() if block["score"] >= min_score}
        if min_block_length or max_block_length:
            min_block_length = 0 if min_block_length is None else min_block_length
            max_block_length = 0xFFFFFFFF if max_block_length is None else max_block_length
            filtered_blocks = {pichash: block for pichash, block in filtered_blocks.items() if max_block_length >= block["length"] >= min_block_length}
        unique_blocks = filtered_blocks
        number_of_unique_blocks = len(filtered_blocks)
        block_pagination = Pagination(request, number_of_unique_blocks, limit=100, query_param="blkp")
        index = 0
        for pichash, result in sorted(unique_blocks.items(), key=lambda x: x[1]["score"], reverse=True):
            if index >= block_pagination.end_index:
                break
            if index >= block_pagination.start_index:
                yarafied = f"/* picblockhash: {pichash} \n"
                maxlen_ins = max([len(ins[1]) for ins in result["instructions"]])
                for ins in result["instructions"]:
                    yarafied += f" * {ins[1]:{maxlen_ins}} | {ins[2]} {ins[3]}\n"
                yarafied += " */\n"
                yarafied += "{ " + re.sub("(.{80})", "\\1\n", result["escaped_sequence"], 0, re.DOTALL) + " }"
                unique_blocks[pichash]["yarafied"] = yarafied
                paginated_block = result
                paginated_block["key"] = pichash
                paginated_block["yarafied"] = yarafied
                paginated_blocks.append(paginated_block)
            index += 1
    # TODO pass the new result objects as single arguments and then render them in page tabs on the template
    return render_template("result_unique_blocks.html", job_info=job_info, family_entry=family_entry, sample_id=sample_id, yara_rule=yara_rule, statistics=blocks_statistics, results=paginated_blocks, blkp=block_pagination, active_tab=active_tab)

def result_matches_for_sample_or_query(job_info, matching_result: MatchingResult):
    score_color_provider = ScoreColorProvider()
    filtered_family_id = parse_integer_query_param(request, "famid")
    filtered_sample_id = parse_integer_query_param(request, "samid")
    filtered_function_id = parse_integer_query_param(request, "funid")
    other_function_id = parse_integer_query_param(request, "ofunid")
    filter_action = parse_str_query_param(request, "filter_button_action")
    # generic filtering on family/sample results
    filter_direct_min_score = parse_integer_query_param(request, "filter_direct_min_score")
    filter_direct_nonlib_min_score = parse_integer_query_param(request, "filter_direct_nonlib_min_score")
    filter_frequency_min_score = parse_integer_query_param(request, "filter_frequency_min_score")
    filter_frequency_nonlib_min_score = parse_integer_query_param(request, "filter_frequency_nonlib_min_score")
    filter_unique_only = parse_checkbox_query_param(request, "filter_unique_only")
    filter_exclude_own_family = parse_checkbox_query_param(request, "filter_exclude_own_family")
    filter_family_name = parse_str_query_param(request, "filter_family_name")
    # generic filtering of function results
    filter_function_min_score = parse_integer_query_param(request, "filter_function_min_score")
    filter_function_max_score = parse_integer_query_param(request, "filter_function_max_score")
    filter_function_offset = parse_integer_query_param(request, "filter_function_offset")
    filter_max_num_families = parse_integer_query_param(request, "filter_max_num_families")
    filter_min_num_samples = parse_integer_query_param(request, "filter_min_num_samples")
    filter_max_num_samples = parse_integer_query_param(request, "filter_max_num_samples")
    filter_exclude_library = parse_checkbox_query_param(request, "filter_exclude_library")
    filter_exclude_pic = parse_checkbox_query_param(request, "filter_exclude_pic")
    filter_func_unique = parse_checkbox_query_param(request, "filter_func_unique")
    if (all(flag is None for flag in [filter_direct_min_score, filter_frequency_min_score, filter_family_name,
                filter_function_min_score, filter_function_max_score, filter_min_num_samples, filter_max_num_samples, filter_max_num_families, filter_function_offset])
            and not any([filter_unique_only, filter_exclude_own_family, filter_exclude_library, filter_exclude_pic, filter_func_unique])
            and not filter_action == "clear"):
        # load default filters
        user_id = get_session_user_id()
        # adjust filters based on family/sample filtering
        filter_values = get_user_result_filters(user_id)
        if filtered_family_id is None and filtered_sample_id is None and filtered_function_id is None:
            filter_values["filter_min_num_samples"] = None
            filter_values["filter_max_num_samples"] = None
            filter_values["filter_max_num_families"] = None
        elif filtered_family_id is not None:
            filter_values["filter_min_num_samples"] = None
            filter_values["filter_max_num_samples"] = None
            filter_values["filter_max_num_families"] = None
        elif filtered_sample_id is not None:
            filter_values["filter_min_num_samples"] = None
            filter_values["filter_max_num_samples"] = None
            filter_values["filter_max_num_families"] = None
    elif filter_action == "clear":
        filter_values = {
            "filter_direct_min_score": None,
            "filter_direct_nonlib_min_score": None,
            "filter_frequency_min_score": None,
            "filter_frequency_nonlib_min_score": None,
            "filter_unique_only": None,
            "filter_exclude_own_family": None,
            "filter_family_name": None,
            "filter_function_min_score": None,
            "filter_function_max_score": None,
            "filter_function_offset": None,
            "filter_max_num_families": None,
            "filter_min_num_samples": None,
            "filter_max_num_samples": None,
            "filter_exclude_library": None,
            "filter_exclude_pic": None,
            "filter_func_unique": None,
        }
    else:
        filter_values = {
            "filter_direct_min_score": filter_direct_min_score,
            "filter_direct_nonlib_min_score": filter_direct_nonlib_min_score,
            "filter_frequency_min_score": filter_frequency_min_score,
            "filter_frequency_nonlib_min_score": filter_frequency_nonlib_min_score,
            "filter_unique_only": filter_unique_only,
            "filter_exclude_own_family": filter_exclude_own_family,
            "filter_family_name": filter_family_name,
            "filter_function_min_score": filter_function_min_score,
            "filter_function_max_score": filter_function_max_score,
            "filter_function_offset": filter_function_offset,
            "filter_max_num_families": filter_max_num_families,
            "filter_min_num_samples": filter_min_num_samples,
            "filter_max_num_samples": filter_max_num_samples,
            "filter_exclude_library": filter_exclude_library,
            "filter_exclude_pic": filter_exclude_pic,
            "filter_func_unique": filter_func_unique,
        }
    matching_result.setFilterValues(filter_values)
    matching_result.getUniqueFamilyMatchInfoForSample(None)
    matching_result.applyFilterValues()

    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    # filtered for family
    if filtered_family_id is not None and client.isFamilyId(filtered_family_id):
        matching_result.filterToFamilyId(filtered_family_id)
        create_match_diagram(current_app, job_info.job_id, matching_result, filtered_family_id=filtered_family_id)
        sample_pagination = Pagination(request, matching_result.num_sample_matches, limit=10, query_param="samp")
        function_pagination = Pagination(request, len(matching_result.getAggregatedFunctionMatches()), query_param="funp")
        return render_template("result_compare_family.html", famid=filtered_family_id, job_info=job_info, samp=sample_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider) 
    # filtered for sample
    elif filtered_sample_id is not None and client.isSampleId(filtered_sample_id):
        matching_result.filterToSampleId(filtered_sample_id)
        create_match_diagram(current_app, job_info.job_id, matching_result, filtered_sample_id=filtered_sample_id)
        filtered_sample_entry = client.getSampleById(filtered_sample_id)
        matching_result.other_sample_entry = filtered_sample_entry
        # get offsets for matched functions
        matched_function_ids = list(set([f.matched_function_id for f in matching_result.filtered_function_matches]))
        matched_function_entries_by_id = client.getFunctionsByIds(matched_function_ids)
        for function_match in matching_result.filtered_function_matches:
            function_match.matched_offset = matched_function_entries_by_id[function_match.matched_function_id].offset
        sample_pagination = Pagination(request, 1, limit=10, query_param="samp")
        function_pagination = Pagination(request, len(matching_result.getAggregatedFunctionMatches()), query_param="funp")
        return render_template("result_compare_sample.html", samid=filtered_sample_id, job_info=job_info, samp=sample_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider) 
    # filter for function - treat family/sample part as if there was no filter
    elif filtered_function_id is not None and filtered_function_id in matching_result.function_id_to_family_ids_matched:
        if not matching_result.is_query:
            create_match_diagram(current_app, job_info.job_id, matching_result, filtered_function_id=filtered_function_id)
        matching_result.filterToFunctionId(filtered_function_id)
        matching_result.filtered_function_matches = sorted(matching_result.filtered_function_matches, key=lambda x: (x.matched_score, x.match_is_pichash, x.matched_family_id, x.matched_sample_id, x.matched_function_id), reverse=True)
        # pull all function_entries, as we want to have their offsets
        matched_function_ids = list(set([f.matched_function_id for f in matching_result.filtered_function_matches]))
        matched_function_entries_by_id = client.getFunctionsByIds(matched_function_ids)
        for function_match in matching_result.filtered_function_matches:
            function_match.matched_offset = matched_function_entries_by_id[function_match.matched_function_id].offset
        # set up pagination
        family_pagination = Pagination(request, matching_result.num_family_matches, limit=10, query_param="famp")
        function_pagination = Pagination(request, matching_result.num_function_matches, query_param="funp")
        return render_template("result_compare_function.html", funid=filtered_function_id, job_info=job_info, famp=family_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider) 
    # 1vs1 result
    elif job_info.parameters.startswith("getMatchesForSampleVs"):
        # we need to slice function matches ourselves based on pagination
        function_pagination = Pagination(request, matching_result.num_function_matches, query_param="funp")
        return render_template("result_compare_vs.html", job_info=job_info, matching_result=matching_result, funp=function_pagination, scp=score_color_provider)
    # unfiltered / default
    else:
        create_match_diagram(current_app, job_info.job_id, matching_result)
        family_pagination = Pagination(request, matching_result.num_family_matches, limit=10, query_param="famp")
        library_pagination = Pagination(request, matching_result.num_library_matches, limit=10, query_param="libp")
        function_pagination = Pagination(request, len(matching_result.getAggregatedFunctionMatches()), query_param="funp")
        return render_template("result_compare_all.html", job_info=job_info, famp=family_pagination, libp=library_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider) 


def result_matches_for_cross(job_info, result_json):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    samples = []
    sample_ids = [int(id) for id in next(iter(result_json.values()))["clustered_sequence"]]
    for sample_id in sample_ids:
        sample_entry = client.getSampleById(sample_id)
        if sample_entry:
            samples.append(sample_entry)
        else:
            reason = f"MCRIT was not able to retrieve information for all samples specified in the original job task. This might be a result of having deleted samples from the database since it was processed. Please consider starting a new job."
            return render_template("result_corrupted.html", reason=reason, matching_result=job_info)
    custom_order = request.args.get('custom','')
    samples_by_method = {}
    sample_indices = {}
    for method, method_results in result_json.items():
        if custom_order:
            order = custom_order.split(',')
        elif "clustered_sequence" in method_results:
            order = method_results["clustered_sequence"]
        else:
            order = None
        ordered_samples = []
        if order:
            for order_sample_id in order:
                for sample in samples:
                    if str(sample.sample_id) == str(order_sample_id):
                        ordered_samples.append(sample)
                        break
                else:
                    reason = f"MCRIT was not able to produce the chosen custom ordering, as some sample_ids are not part of the cross compare originally specified."
                    return render_template("result_corrupted.html", reason=reason, matching_result=result_json)
        if ordered_samples != []:
            samples_by_method[method] = ordered_samples
        else:
            samples_by_method[method] = samples
        sample_indices[method] = [x for index, x in enumerate([sample.sample_id for sample in samples_by_method[method]]) if (index+1) % 5 == 0]
    return render_template('result_cross.html',
        is_corrupted=False,
        samples=samples_by_method,
        sample_indices = sample_indices,
        job_info=job_info,
        sample_to_job_id=get_sample_to_job_id(job_info),
        matching_matches={method: result_json[method]["matching_matches"] for method in result_json.keys()},
        matching_percent={method: result_json[method]["matching_percent"] for method in result_json.keys()},
        score_to_color=score_to_color,
    )


################################################################
# Link Hunting
################################################################

@bp.route('/linkhunt/<job_id>')
@mcrit_server_required
@visitor_required
# TODO:  refactor, simplify
def linkhunt(job_id):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    # check if we have the respective report already locally cached
    result_json = load_cached_result(current_app, job_id)
    job_info = client.getJobData(job_id)
    if not result_json:
        # otherwise obtain result report from remote
            result_json = client.getResultForJob(job_id)
            if result_json:
                cache_result(current_app, job_info, result_json)
    if result_json:
        # TODO validation - only parse to matching_result if this data type is appropriate 
        # re-format result report for visualization and choose respective template
        if job_info is None:
            return render_template("result_invalid.html", job_id=job_id)
        elif job_info.parameters.startswith("getMatchesForSample"):
            matching_result = MatchingResult.fromDict(result_json)
            return linkhunt_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForSmdaReport"):
            matching_result = MatchingResult.fromDict(result_json)
            return linkhunt_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForMappedBinary"):
            matching_result = MatchingResult.fromDict(result_json)
            return linkhunt_for_sample_or_query(job_info, matching_result)
        elif job_info.parameters.startswith("getMatchesForUnmappedBinary"):
            matching_result = MatchingResult.fromDict(result_json)
            return linkhunt_for_sample_or_query(job_info, matching_result)
    elif job_info:
        # if we are not done processing, list job data
        return render_template("job_in_progress.html", job_info=job_info)
    else:
        # if we can't find job or result, we have to assume the job_id was invalid
        return render_template("result_incompatible.html", job_id=job_id)

def linkhunt_for_sample_or_query(job_info, matching_result: MatchingResult):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    score_color_provider = ScoreColorProvider()
    # generic filtering of function results
    filter_action = parse_str_query_param(request, "filter_button_action")
    filter_min_score = parse_integer_query_param(request, "filter_min_score")
    filter_lib_min_score = parse_integer_query_param(request, "filter_lib_min_score")
    filter_link_score = parse_integer_query_param(request, "filter_link_score")
    filter_min_size = parse_integer_query_param(request, "filter_min_size")
    filter_min_offset = parse_integer_query_param(request, "filter_min_offset")
    filter_max_offset = parse_integer_query_param(request, "filter_max_offset")
    filter_unpenalized_family_count = parse_integer_query_param(request, "filter_unpenalized_family_count")
    filter_exclude_families = parse_integer_list_query_param(request, "filter_exclude_families")
    filter_exclude_samples = parse_integer_list_query_param(request, "filter_exclude_samples")
    filter_strongest_per_family = parse_checkbox_query_param(request, "filter_strongest_per_family")
    if (all(flag is None for flag in [filter_min_score, filter_lib_min_score, filter_link_score, filter_min_size,
                filter_min_offset, filter_max_offset, filter_exclude_families, filter_exclude_samples])
                and not filter_strongest_per_family
                and not filter_action == "clear"):
        # specify default filters
        filter_min_score = 65
        filter_lib_min_score = 80
        filter_link_score = 30
        filter_min_size = 50
        filter_min_offset = None
        filter_max_offset = None
        # own family id
        filter_exclude_families = [matching_result.reference_sample_entry.family_id]
        filter_exclude_samples = []
        filter_unpenalized_family_count = 2
        filter_strongest_per_family = True
    elif filter_action == "clear":
        filter_min_score = None
        filter_lib_min_score = None
        filter_link_score = None
        filter_min_size = None
        filter_min_offset = None
        filter_max_offset = None
        # own family id
        filter_exclude_families = None
        filter_exclude_samples = None
        filter_unpenalized_family_count = 2
        filter_strongest_per_family = False
    filter_values = {
        "filter_min_score": filter_min_score,
        "filter_lib_min_score": filter_lib_min_score,
        "filter_link_score": filter_link_score,
        "filter_min_size": filter_min_size,
        "filter_min_offset": filter_min_offset,
        "filter_max_offset": filter_max_offset,
        "filter_exclude_families": ", ".join([str(famid) for famid in filter_exclude_families]) if filter_exclude_families is not None else "",
        "filter_exclude_samples": ", ".join([str(samid) for samid in filter_exclude_samples]) if filter_exclude_samples is not None else "",
        "filter_unpenalized_family_count": filter_unpenalized_family_count,
        "filter_strongest_per_family": filter_strongest_per_family,
    }
    matching_result.setFilterValues(filter_values)
    link_hunt_result = matching_result.getLinkHuntResults(filter_min_score, filter_lib_min_score, filter_min_size, filter_min_offset, filter_max_offset, filter_unpenalized_family_count, filter_exclude_families, filter_exclude_samples, filter_strongest_per_family)

    function_entries = client.getFunctionsBySampleId(matching_result.reference_sample_entry.sample_id)
    # TODO: probably need to paginate them as well
    link_clusters = matching_result.clusterLinkHuntResult(function_entries, link_hunt_result)
    link_clusters = sorted([l for l in link_clusters if len(l["links"]) > 1], key=lambda x: x["score"], reverse=True)

    if filter_link_score:
        link_clusters = [l for l in link_clusters if l["score"] > filter_link_score]
        link_hunt_result = [l for l in link_hunt_result if l.matched_link_score > filter_link_score]

    function_pagination = Pagination(request, len(link_hunt_result), query_param="funp")
    return render_template("linkhunt.html", job_info=job_info, funp=function_pagination, matching_result=matching_result, lc=link_clusters, lhr=link_hunt_result, scp=score_color_provider)


################################################################
# Listing Job information
################################################################

@bp.route('/jobs',methods=('GET', 'POST'))
@mcrit_server_required
@visitor_required
def jobs():
    query = None
    if request.method == 'POST':
        query = request.form['Search']
    # used for job/method collections
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    statistics = client.getQueueStatistics()
    job_template = Job(None, None)
    # dynamically create the job page with nested menu based on groups from statistics and Job.method_types
    active_category = request.args.get('active', None)
    summarized_groups = {"matching": 0, "query": 0, "blocks": 0, "minhashing": 0, "collection": 0}
    for group in summarized_groups.keys():
        for category in job_template.method_types[group]:
            if category in statistics:
                summarized_groups[group] += sum(statistics[category].values())
    if active_category is None:
        for category in job_template.method_types["all"]:
            if category in statistics:
                active_category = category
                break
    # build menu information
    jobs = None
    pagination = None
    menu_configuration = {}
    if active_category:
        menu_configuration = {
            "menu": [
                {"group": "matching", "title": f"Matching ({summarized_groups['matching']})", "active": True, "available": True, "submenu": [
                    {"title": f"getMatchesForSample ({sum(statistics['getMatchesForSample'].values())})", "active": "getMatchesForSample" == active_category, "available": "getMatchesForSample" in statistics},
                    {"title": f"getMatchesForSampleVs ({sum(statistics['getMatchesForSampleVs'].values())})", "active": "getMatchesForSampleVs" == active_category, "available": "getMatchesForSampleVs" in statistics},
                    {"title": f"combineMatchesToCross ({sum(statistics['combineMatchesToCross'].values()) if 'combineMatchesToCross' in statistics else 0})", "active": "combineMatchesToCross" == active_category, "available": "combineMatchesToCross" in statistics},
                ]}, 
                {"group": "query", "title": f"Query ({summarized_groups['query']})", "active": False, "available": True, "submenu": [
                    {"title": f"getMatchesForUnmappedBinary ({sum(statistics['getMatchesForUnmappedBinary'].values())})", "active": "getMatchesForUnmappedBinary" == active_category, "available": "getMatchesForUnmappedBinary" in statistics},
                ]}, 
                {"title": "Blocks", "active": False, "available": False}, 
                {"title": "Minhashing", "active": False, "available": False}, 
                {"title": "Collection", "active": False, "available": False}, 
            ],
            "statistics": statistics
        }
        max_count = sum(statistics[active_category].values())
        pagination = Pagination(request, max_count, query_param="p")
        jobs = client.getQueueData(start=pagination.start_index, limit=pagination.limit, method=active_category)
    # TODO decide if there's more to fix and possibly beef up the statistics with everything needed to dynamically derive the nested page layout in jobs.html
    return render_template('jobs.html', active=active_category, jobs=jobs, menu_configuration=menu_configuration, p=pagination, query=query)


@bp.route('/jobs/<job_id>')
@mcrit_server_required
@visitor_required
def job_by_id(job_id):
    auto_refresh = 0
    auto_forward = 0
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    suppress_processing_message = False
    FMT = '%Y-%m-%d-%H:%M:%S'
    try:
        auto_refresh = int(request.args.get("refresh"))
    except TypeError:
        pass
    try:
        auto_forward = int(request.args.get("forward"))
    except TypeError:
        pass

    job_info = client.getJobData(job_id)
    if auto_refresh and job_info and job_info.is_failed:
        auto_refresh = 0
        suppress_processing_message = True
        flash('The job failed!', category='error')

    if job_info is None:
        return render_template("job_invalid.html", job_id=job_id)

    if job_info.finished_at != None:
        if auto_forward:
            if 'addBinarySample' in job_info.parameters:
                suppress_processing_message = True
                flash('Sample submitted successfully!', category='success')
            return redirect(url_for('data.result', job_id=job_id))
    if 'addBinarySample' in job_info.parameters and not suppress_processing_message and auto_refresh:
        flash('We received your sample, currently processing!', category='info')
    child_jobs = sorted([client.getJobData(id) for id in job_info.all_dependencies], key=lambda x: x.number)
    return render_template('job_overview.html', job_info=job_info, auto_refresh=auto_refresh, child_jobs=child_jobs)


@bp.route('/jobs/<job_id>/delete')
@mcrit_server_required
@visitor_required
def delete_job_by_id(job_id):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    job_data = client.getJobData(job_id)
    raise NotImplementedError("Implement me!")


################################################################
# Binary submission
################################################################

@bp.route('/request_filename_info', methods=['POST'])
@mcrit_server_required
@contributor_required
def request_filename_info():
    try:
        filename = json.loads(request.data)["filename"]
    except Exception:
        filename = ""
    result = {}
    if 'dump' in filename:
        result['dump'] = True
        result['bitness'] = parseBitnessFromFilename(filename)
        base_address = parseBaseAddrFromFilename(filename)
        result['baseaddress'] = "" if not base_address else hex(base_address)
    else:
        result['dump'] = False
    return json.dumps(result), 200


@bp.route('/submit_or_query', methods=('POST',))
@mcrit_server_required
@contributor_required
def submit_or_query():
    form_type = request.form['form_type']
    # NOTE: we do not use redirect to prevent resending of large file data
    if form_type == "query_form":
        return analyze_query()
        # return redirect(url_for("analyze.query"), code=307)
    elif form_type == "submit_form":
        return submit()
        # return redirect(url_for("data.submit"), code=307)


@bp.route('/submit',methods=('GET', 'POST'))
@mcrit_server_required
@contributor_required
def submit():
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    if request.method == 'POST':
        f = request.files.get('file')
        if f is None:
            flash("Please upload a file", category='error')
            return "", 400 # Bad Request
        family = request.form['family']
        version = request.form['version']
        bitness = None
        base_address = None
        is_dump = request.form['options'] == 'dumped'
        if is_dump:
            bitness = int(request.form['bitness'])
            base_address = int(request.form['base_address'], 16)

        binary_content = f.read()
        # check here if it is already part of corpus
        upload_sha256 = hashlib.sha256(binary_content).hexdigest()
        sample_entry = client.getSampleBySha256(upload_sha256)
        if sample_entry is None:
            # NOTE: This flash is done on redirect target
            # flash('We received your sample, currently processing!', category='info')
            with open(os.sep.join([current_app.instance_path, "temp", "uploads", upload_sha256]), "wb") as fout:
                fout.write(binary_content)
            job_id = client.addBinarySample(binary_content, filename=f.filename, family=family, version=version, is_dump=is_dump, base_addr=base_address, bitness=bitness)
            return url_for('data.job_by_id', job_id=job_id, refresh=3, forward=1), 202 # Accepted
        else:
            flash('Sample was already in database', category='warning')
            return url_for('explore.sample_by_id', sample_id=sample_entry.sample_id), 202 # Accepted
    all_families = client.getFamilies()
    family_names = [family_entry.family_name for family_entry in all_families.values()]
    return render_template('submit.html', families=family_names, show_submit_fields=True)
