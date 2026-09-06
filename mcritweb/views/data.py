import hashlib
import os
import re
from datetime import datetime

from flask import Blueprint, Response, current_app, flash, json, redirect, render_template, request, send_from_directory, session, url_for
from mcrit.queue.LocalQueue import Job
from mcrit.storage.FunctionEntry import FunctionEntry
from mcrit.storage.MatchedFunctionEntry import MatchedFunctionEntry
from mcrit.storage.MatchingResult import MatchingResult
from mcrit.storage.SampleEntry import SampleEntry
from mcrit.storage.UniqueBlocksResult import UniqueBlocksResult
from smda.common.SmdaReport import SmdaReport

from mcritweb.db import UserColumnSettings, UserFilters
from mcritweb.views.analyze import query as analyze_query
from mcritweb.views.authentication import contributor_required, visitor_required
from mcritweb.views.client import get_client
from mcritweb.views.cross_compare import get_sample_to_job_id, score_to_color
from mcritweb.views.functiondiff import get_matches_node_colors
from mcritweb.views.MatchReportRenderer import MatchReportRenderer
from mcritweb.views.pagination import Pagination
from mcritweb.views.params import (
    parse_checkbox_query_param,
    parse_integer_list_query_param,
    parse_integer_query_param,
    parse_str_query_param,
    parseBaseAddrFromFilename,
    parseBitnessFromFilename,
    slider_position_for_band_range,
)
from mcritweb.views.ScoreColorProvider import ScoreColorProvider
from mcritweb.views.utility import get_session_user_id, mcrit_server_required

bp = Blueprint('data', __name__, url_prefix='/data')

################################################################
# Helper functions
################################################################

def load_cached_result(app, job_id):
    matching_result = {}
    cache_path = os.sep.join([app.instance_path, "cache", "results"])
    for filename in os.listdir(cache_path):
        if job_id in filename and filename.endswith("json"):
            with open(cache_path + os.sep + filename) as fin:
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
@visitor_required
def diagram_file(filename):
    cache_path = os.sep.join([current_app.instance_path, "cache", "diagrams"])
    return send_from_directory(cache_path, filename)


################################################################
# Import + Export
################################################################

@bp.route('/import',methods=('GET', 'POST'))
@contributor_required
@mcrit_server_required
def import_view():
    if request.method == 'POST':
        # dropping the wrong file into a dropzone is ordinary user input, not an
        # exceptional condition - report it the way import_complete already does
        # instead of letting json.load or the client's own type check raise a 500
        try:
            import_data = json.load(request.files['file'])
        except (KeyError, ValueError):
            import_data = None
        if isinstance(import_data, dict):
            client = get_client()
            session["last_import"] = client.addImportData(import_data)
        else:
            flash("This doesn't seem to be valid MCRIT data in JSON format", category='error')
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
@contributor_required
@mcrit_server_required
def export_view():
    if request.method == 'POST':
        requested_samples = request.form['samples']
        client = get_client()
        if requested_samples == "":
            export_file = json.dumps(client.getExportData())
            return Response(
                export_file,
                mimetype='application/json',
                headers={"Content-disposition":
                        "attachment; filename=export_all_samples.json"})
        # NOTE it might be nice to allow [<number>, <number>-<number>, ...] to enable 
        # spans of consecutive sample_ids
        elif re.match(r"^\d+(?:[\s]*,[\s]*\d+)*$", requested_samples):
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
@contributor_required
@mcrit_server_required
def specific_export(type, item_id):
    client = get_client()
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
    # <type> is unconstrained, so anything but the two known values used to fall off
    # the end of this function and return None, which Flask answers with a 500
    flash(f'"{type}" cannot be exported - use "family" or "samples".', category='error')
    return redirect(url_for('data.export_view'))

################################################################
# Direct Function Matching
################################################################

@bp.route('/matches/function/<function_id_a>/<function_id_b>')
@visitor_required
@mcrit_server_required
def match_functions(function_id_a, function_id_b):
    client = get_client()
    if client.isFunctionId(function_id_a) and client.isFunctionId(function_id_b):
        match_info = client.getMatchFunctionVs(function_id_a, function_id_b)
        print(match_info)
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
            # the template serialises this with |tojson, which escapes for a script
            # context - pre-serialising here would hand it a string to re-encode
            node_colors=node_colors
        )
    flash("One of the function_ids is not valid.", category='error')
    return render_template("index.html")

################################################################
# Result presentation
################################################################

@bp.route('/result/<job_id>')
@visitor_required
@mcrit_server_required
# TODO:  refactor, simplify
def result(job_id):
    client = get_client()
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
        elif job_info.parameters in ["rebuildIndex()", "recalculatePicHashes()", "recalculateMinHashes()"]:
            return render_template("result_maintenance.html", result=result_json, job_info=job_info)
    elif job_info and not (job_info.is_finished or job_info.is_failed or job_info.is_terminated):
        # if we are not done processing, list job data
        return render_template("job_in_progress.html", job_info=job_info)
    else:
        # if we can't find job or result, we have to assume the job_id was invalid
        return render_template("result_invalid.html", job_id=job_id)

def build_yara_rule(job_info, blocks_result, blocks_statistics):
    ubr = UniqueBlocksResult.fromDict(blocks_result)
    yara_rule = ubr.generateYaraRule(wrap_at=40)
    return yara_rule

def result_unique_blocks(job_info, blocks_result: dict):
    client = get_client()
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
        block_pagination = Pagination(request, number_of_unique_blocks, limit=100, query_param="blkp", limit_param="blkl")
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
                yarafied += "{ " + re.sub(r"(.{80})", "\\1\n", result["escaped_sequence"], flags=re.DOTALL) + " }"
                unique_blocks[pichash]["yarafied"] = yarafied
                paginated_block = result
                paginated_block["key"] = pichash
                paginated_block["yarafied"] = yarafied
                paginated_blocks.append(paginated_block)
            index += 1
    # TODO pass the new result objects as single arguments and then render them in page tabs on the template
    return render_template("result_unique_blocks.html", job_info=job_info, family_entry=family_entry, sample_id=sample_id, yara_rule=yara_rule, statistics=blocks_statistics, results=paginated_blocks, blkp=block_pagination, active_tab=active_tab)

#: Shown when a stored result names something the backend can no longer resolve. The
#: cross-compare path has said this about samples for a long time; issue #96 is the
#: same situation one level down, where the missing thing is a function.
MISSING_ENTRIES_REASON = "MCRIT was not able to retrieve information for all functions referenced by this result. This might be a result of having deleted samples from the database since it was processed. Please consider starting a new job."


def assign_matched_offsets(client, function_matches):
    """Attach the offset of each matched function, in place.

    Returns False when the backend no longer has every function the result names.
    `getFunctionsByIds` answers only the entries that still exist, and a stored
    result refers to functions by id, so deleting a sample after a job finished
    leaves ids behind that resolve to nothing. Indexing the lookup directly made
    that a KeyError and a 500 on a report that is otherwise still readable - see
    issue #96. The caller decides what to do about it; all three call sites in this
    module render `result_corrupted.html`, which is what the cross-compare path
    already does for a missing sample.
    """
    matched_function_ids = list({match.matched_function_id for match in function_matches})
    matched_function_entries_by_id = client.getFunctionsByIds(matched_function_ids) or {}
    is_complete = True
    for function_match in function_matches:
        function_entry = matched_function_entries_by_id.get(function_match.matched_function_id)
        if function_entry is None:
            is_complete = False
            continue
        function_match.matched_offset = function_entry.offset
    return is_complete


def result_matches_for_sample_or_query(job_info, matching_result: MatchingResult):
    score_color_provider = ScoreColorProvider()
    filtered_family_id = parse_integer_query_param(request, "famid")
    filtered_sample_id = parse_integer_query_param(request, "samid")
    filtered_function_id = parse_integer_query_param(request, "funid")
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
    user_id = get_session_user_id()
    if (all(flag is None for flag in [filter_direct_min_score, filter_frequency_min_score, filter_family_name,
                filter_function_min_score, filter_function_max_score, filter_min_num_samples, filter_max_num_samples, filter_max_num_families, filter_function_offset])
            and not any([filter_unique_only, filter_exclude_own_family, filter_exclude_library, filter_exclude_pic, filter_func_unique])
            and not filter_action == "clear"):
        # load default filters
        # adjust filters based on family/sample filtering
        user_filters = UserFilters.fromDb(user_id)
        # if we don't have them yet, create them
        if user_filters is None:
            user_filters = UserFilters.fromDict(user_id, {})
            user_filters.saveToDb()
        filter_values = user_filters.toDict()
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

    client = get_client()

    # load user column setup from database
    user_column_settings = UserColumnSettings.fromDb(user_id)
    # if we don't have them yet, create them
    if user_column_settings is None:
        user_column_settings = UserColumnSettings(user_id)
        user_column_settings.saveToDb()
    ucs_dict = user_column_settings.toUserColumnSettings()
    user_column_setup_family_library = ucs_dict["result_family_table"]["active"]
    user_column_setup_function_all = ucs_dict["result_function_unfiltered_table"]["active"]
    # note that in getMatchesForSampleVs - we can never determine if a function is unique across the data set, so we ignore the field
    user_column_setup_function_sample = ucs_dict["result_function_sample_filtered_table"]["active"]
    user_column_setup_function_function = ucs_dict["result_function_function_filtered_table"]["active"]
    # filtered for family
    if filtered_family_id is not None and client.isFamilyId(filtered_family_id):
        matching_result.filterToFamilyId(filtered_family_id)
        create_match_diagram(current_app, job_info.job_id, matching_result, filtered_family_id=filtered_family_id)
        sample_pagination = Pagination(request, matching_result.num_sample_matches, limit=10, query_param="samp", limit_param="sampl")
        function_pagination = Pagination(request, len(matching_result.getAggregatedFunctionMatches()), limit=100, query_param="funp", limit_param="funl")
        return render_template("result_compare_family.html", famid=filtered_family_id, job_info=job_info, samp=sample_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider, ucs_famlib=user_column_setup_family_library, ucs_functions=user_column_setup_function_all) 
    # filtered for sample
    elif filtered_sample_id is not None and client.isSampleId(filtered_sample_id):
        matching_result.filterToSampleId(filtered_sample_id)
        create_match_diagram(current_app, job_info.job_id, matching_result, filtered_sample_id=filtered_sample_id)
        filtered_sample_entry = client.getSampleById(filtered_sample_id)
        matching_result.other_sample_entry = filtered_sample_entry
        # get offsets for matched functions
        if not assign_matched_offsets(client, matching_result.filtered_function_matches):
            return render_template("result_corrupted.html", reason=MISSING_ENTRIES_REASON, job_info=job_info)
        sample_pagination = Pagination(request, 1, limit=10, query_param="samp", limit_param="sampl")
        function_pagination = Pagination(request, len(matching_result.getAggregatedFunctionMatches()), limit=100, query_param="funp", limit_param="funl")
        return render_template("result_compare_sample.html", samid=filtered_sample_id, job_info=job_info, samp=sample_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider, ucs_famlib=user_column_setup_family_library, ucs_functions=user_column_setup_function_sample) 
    # filter for function - treat family/sample part as if there was no filter
    elif filtered_function_id is not None and filtered_function_id in matching_result.function_id_to_family_ids_matched:
        if not matching_result.is_query:
            create_match_diagram(current_app, job_info.job_id, matching_result, filtered_function_id=filtered_function_id)
        matching_result.filterToFunctionId(filtered_function_id)
        matching_result.filtered_function_matches = sorted(matching_result.filtered_function_matches, key=lambda x: (x.matched_score, x.match_is_pichash, x.matched_family_id, x.matched_sample_id, x.matched_function_id), reverse=True)
        # pull all function_entries, as we want to have their offsets
        if not assign_matched_offsets(client, matching_result.filtered_function_matches):
            return render_template("result_corrupted.html", reason=MISSING_ENTRIES_REASON, job_info=job_info)
        # set up pagination
        family_pagination = Pagination(request, matching_result.num_family_matches, limit=10, query_param="famp", limit_param="fampl")
        function_pagination = Pagination(request, matching_result.num_function_matches, limit=100, query_param="funp", limit_param="funl")
        return render_template("result_compare_function.html", funid=filtered_function_id, job_info=job_info, famp=family_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider, ucs_famlib=user_column_setup_family_library, ucs_functions=user_column_setup_function_function) 
    # 1 vs 1 result
    elif job_info.parameters.startswith("getMatchesForSampleVs("):
        # get offsets for matched functions
        if not assign_matched_offsets(client, matching_result.filtered_function_matches):
            return render_template("result_corrupted.html", reason=MISSING_ENTRIES_REASON, job_info=job_info)
        # we need to slice function matches ourselves based on pagination
        function_pagination = Pagination(request, matching_result.num_function_matches, limit=100, query_param="funp", limit_param="funl")
        return render_template("result_compare_vs.html", job_info=job_info, matching_result=matching_result, funp=function_pagination, scp=score_color_provider, ucs_famlib=user_column_setup_family_library, ucs_functions=user_column_setup_function_sample)
    # unfiltered / default -> also 1 vs group
    else:
        create_match_diagram(current_app, job_info.job_id, matching_result)
        family_pagination = Pagination(request, matching_result.num_family_matches, limit=10, query_param="famp", limit_param="fampl")
        library_pagination = Pagination(request, matching_result.num_library_matches, limit=10, query_param="libp", limit_param="libl")
        function_pagination = Pagination(request, len(matching_result.getAggregatedFunctionMatches()), limit=100, query_param="funp", limit_param="funl")
        return render_template("result_compare_all.html", job_info=job_info, famp=family_pagination, libp=library_pagination, funp=function_pagination, matching_result=matching_result, scp=score_color_provider, ucs_famlib=user_column_setup_family_library, ucs_functions=user_column_setup_function_all)


def result_matches_for_cross(job_info, result_json):
    client = get_client()
    samples = []
    sample_ids = [int(id) for id in next(iter(result_json.values()))["clustered_sequence"]]
    for sample_id in sample_ids:
        sample_entry = client.getSampleById(sample_id)
        if sample_entry:
            samples.append(sample_entry)
        else:
            reason = "MCRIT was not able to retrieve information for all samples specified in the original job task. This might be a result of having deleted samples from the database since it was processed. Please consider starting a new job."
            return render_template("result_corrupted.html", reason=reason, job_info=job_info)
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
                    reason = "MCRIT was not able to produce the chosen custom ordering, as some sample_ids are not part of the cross compare originally specified."
                    return render_template("result_corrupted.html", reason=reason, job_info=result_json)
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
@visitor_required
@mcrit_server_required
# TODO:  refactor, simplify
def linkhunt(job_id):
    client = get_client()
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
    client = get_client()
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
    link_clusters = sorted([cluster for cluster in link_clusters if len(cluster["links"]) > 1], key=lambda x: x["score"], reverse=True)

    if filter_link_score:
        link_clusters = [cluster for cluster in link_clusters if cluster["score"] > filter_link_score]
        link_hunt_result = [link for link in link_hunt_result if link.matched_link_score > filter_link_score]

    function_pagination = Pagination(request, len(link_hunt_result), limit=100, query_param="funp", limit_param="funl")
    return render_template("linkhunt.html", job_info=job_info, funp=function_pagination, matching_result=matching_result, lc=link_clusters, lhr=link_hunt_result, scp=score_color_provider)


################################################################
# Listing Job information
################################################################

@bp.route('/jobs',methods=('GET', 'POST'))
@visitor_required
@mcrit_server_required
def jobs():
    query = None
    if request.method == 'POST':
        query = request.form['Search']
    # used for job/method collections
    client = get_client()
    # sort order
    ascending = request.args.get('ascending', 'false').lower() == "true"
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
    # if we filter by state, don't filter by type
    state_category = request.args.get('state', None)
    if state_category:
        active_category = None
    totals = {"queued": 0, "in_progress": 0, "finished": 0, "failed": 0, "terminated": 0}
    for category, status_dict in statistics.items():
        for state, count in status_dict.items():
            if state not in totals:
                totals[state] = 0
            totals[state] += count
    statistics["totals"] = totals
    # build menu information
    jobs = None
    pagination = None
    menu_configuration = {
        "menu": [
            {"group": "matching", "title": f"Matching ({summarized_groups['matching']})", "active": active_category in ["getMatchesForSample", "getMatchesForSampleVs", "combineMatchesToCross"], "available": True, "submenu": [
                {"name": "getMatchesForSample", "title": f"getMatchesForSample ({sum(statistics['getMatchesForSample'].values()) if 'getMatchesForSample' in statistics else 0})", "active": "getMatchesForSample" == active_category, "available": "getMatchesForSample" in statistics},
                {"name": "getMatchesForSampleVs", "title": f"getMatchesForSampleVs ({sum(statistics['getMatchesForSampleVs'].values()) if 'getMatchesForSampleVs' in statistics else 0})", "active": "getMatchesForSampleVs" == active_category, "available": "getMatchesForSampleVs" in statistics},
                {"name": "combineMatchesToCross", "title": f"combineMatchesToCross ({sum(statistics['combineMatchesToCross'].values()) if 'combineMatchesToCross' in statistics else 0})", "active": "combineMatchesToCross" == active_category, "available": "combineMatchesToCross" in statistics},
            ]}, 
            {"group": "query", "title": f"Query ({summarized_groups['query']})", "active": active_category in ["getMatchesForUnmappedBinary", "getMatchesForMappedBinary", "getMatchesForSmdaReport"], "available": True, "submenu": [
                {"name": "getMatchesForUnmappedBinary", "title": f"getMatchesForUnmappedBinary ({sum(statistics['getMatchesForUnmappedBinary'].values()) if 'getMatchesForUnmappedBinary' in statistics else 0})", "active": "getMatchesForUnmappedBinary" == active_category, "available": "getMatchesForUnmappedBinary" in statistics},
                {"name": "getMatchesForMappedBinary", "title": f"getMatchesForMappedBinary ({sum(statistics['getMatchesForMappedBinary'].values()) if 'getMatchesForMappedBinary' in statistics else 0})", "active": "getMatchesForMappedBinary" == active_category, "available": "getMatchesForMappedBinary" in statistics},
                {"name": "getMatchesForSmdaReport", "title": f"getMatchesForSmdaReport ({sum(statistics['getMatchesForSmdaReport'].values()) if 'getMatchesForSmdaReport' in statistics else 0})", "active": "getMatchesForSmdaReport" == active_category, "available": "getMatchesForSmdaReport" in statistics},
            ]}, 
            {"group": "getUniqueBlocks", "title": f"Blocks ({summarized_groups['blocks']})", "active": "getUniqueBlocks" == active_category, "available": "getUniqueBlocks" in statistics},
            {"group": "minhashing", "title": f"Minhashing ({summarized_groups['minhashing']})", "active": active_category in ["updateMinHashesForSample", "updateMinHashes", "rebuildIndex"], "available": True, "submenu": [
                {"name": "updateMinHashesForSample", "title": f"updateMinHashesForSample ({sum(statistics['updateMinHashesForSample'].values()) if 'updateMinHashesForSample' in statistics else 0})", "active": "updateMinHashesForSample" == active_category, "available": "updateMinHashesForSample" in statistics},
                {"name": "updateMinHashes", "title": f"updateMinHashes ({sum(statistics['updateMinHashes'].values()) if 'updateMinHashes' in statistics else 0})", "active": "updateMinHashes" == active_category, "available": "updateMinHashes" in statistics},
                {"name": "rebuildIndex", "title": f"rebuildIndex ({sum(statistics['rebuildIndex'].values()) if 'rebuildIndex' in statistics else 0})", "active": "rebuildIndex" == active_category, "available": "rebuildIndex" in statistics},
                {"name": "recalculateMinHashes", "title": f"recalculateMinHashes ({sum(statistics['recalculateMinHashes'].values()) if 'recalculateMinHashes' in statistics else 0})", "active": "recalculateMinHashes" == active_category, "available": "recalculateMinHashes" in statistics},
                {"name": "recalculatePicHashes", "title": f"recalculatePicHashes ({sum(statistics['recalculatePicHashes'].values()) if 'recalculatePicHashes' in statistics else 0})", "active": "recalculatePicHashes" == active_category, "available": "recalculatePicHashes" in statistics},
            ]}, 
            {"group": "collection", "title": f"Collection ({summarized_groups['collection']})", "active": active_category in ["addBinarySample", "deleteSample", "modifySample", "deleteFamily", "modifyFamily"], "available": True, "submenu": [
                {"name": "addBinarySample", "title": f"addBinarySample ({sum(statistics['addBinarySample'].values()) if 'addBinarySample' in statistics else 0})", "active": "addBinarySample" == active_category, "available": "addBinarySample" in statistics},
                {"name": "deleteSample", "title": f"deleteSample ({sum(statistics['deleteSample'].values()) if 'deleteSample' in statistics else 0})", "active": "deleteSample" == active_category, "available": "deleteSample" in statistics},
                {"name": "modifySample", "title": f"modifySample ({sum(statistics['modifySample'].values()) if 'modifySample' in statistics else 0})", "active": "modifySample" == active_category, "available": "modifySample" in statistics},
                {"name": "deleteFamily", "title": f"deleteFamily ({sum(statistics['deleteFamily'].values()) if 'deleteFamily' in statistics else 0})", "active": "deleteFamily" == active_category, "available": "deleteFamily" in statistics},
                {"name": "modifyFamily", "title": f"modifyFamily ({sum(statistics['modifyFamily'].values()) if 'modifyFamily' in statistics else 0})", "active": "modifyFamily" == active_category, "available": "modifyFamily" in statistics},
            ]}, 
        ],
        "statistics": statistics
    }
    if active_category is None:
        max_count = statistics["totals"][state_category] if state_category in statistics["totals"] else 0
        pagination = Pagination(request, max_count, limit=25, query_param="p", limit_param="l")
    else:
        max_count = sum(statistics[active_category].values()) if active_category else 0
        pagination = Pagination(request, max_count, limit=25, query_param="p")
    jobs = client.getQueueData(start=pagination.start_index, limit=pagination.limit, method=active_category, state=state_category, ascending=ascending)
    samples_by_id = {}
    families_by_id = {}
    if jobs:
        for job in jobs:
            if job.sample_ids is not None:
                for sample_id in [sid for sid in job.sample_ids if sid not in samples_by_id]:
                    samples_by_id[sample_id] = client.getSampleById(sample_id)
        for job in jobs:
            if job.family_id is not None:
                families_by_id[job.family_id] = client.getFamily(job.family_id)
    return render_template('jobs.html', families=families_by_id, samples=samples_by_id, active=active_category, state=state_category, jobs=jobs, menu_configuration=menu_configuration, p=pagination, query=query)


@bp.route('/jobs/<job_id>')
@visitor_required
@mcrit_server_required
def job_by_id(job_id):
    auto_refresh = 0
    auto_forward = 0
    client = get_client()
    suppress_processing_message = False
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

    if job_info.finished_at is not None:
        if auto_forward:
            if 'addBinarySample' in job_info.parameters:
                suppress_processing_message = True
                flash('Sample submitted successfully!', category='success')
            return redirect(url_for('data.result', job_id=job_id))
    if 'addBinarySample' in job_info.parameters and not suppress_processing_message and auto_refresh:
        flash('We received your sample, currently processing!', category='info')
    # a dependency can be gone by the time its parent is looked at - deleted through this
    # app's own job delete, which also has a "delete every job of this method" form, or
    # cleaned up in the backend - and getJobData answers None for it rather than raising.
    # Sorting that None on .number used to take the whole overview down with a 500.
    resolved_children = [client.getJobData(id) for id in job_info.all_dependencies]
    missing_children = sum(1 for job in resolved_children if job is None)
    child_jobs = sorted([job for job in resolved_children if job is not None], key=lambda x: x.number)
    samples_by_id = {}
    families_by_id = {}
    if child_jobs:
        for job in child_jobs:
            if job.sample_ids is not None:
                for sample_id in [sid for sid in job.sample_ids if sid not in samples_by_id]:
                    samples_by_id[sample_id] = client.getSampleById(sample_id)
        for job in child_jobs:
            if job.family_id is not None:
                families_by_id[job.family_id] = client.getFamily(job.family_id)
    return render_template('job_overview.html', families=families_by_id, samples=samples_by_id, job_info=job_info, auto_refresh=auto_refresh, child_jobs=child_jobs, missing_children=missing_children, can_rerun=is_rerunnable(job_info, child_jobs), configuration_url=configuration_url(job_info, child_jobs))


@bp.route('/jobs/<job_id>/delete', methods=('POST',))
@contributor_required
@mcrit_server_required
def delete_job_by_id(job_id):
    client = get_client()
    print("job to be deleted:", job_id)
    job_info = client.getJobData(job_id)
    print("job info:", job_info)
    if job_id.startswith("state_"):
        state = job_id.replace("state_", "")
        jobs = client.getQueueData(state=state)
        if jobs:
            for job in jobs:
                client.deleteJob(job.job_id)
    elif job_id.startswith("category_"):
        category = job_id.replace("category_", "")
        jobs = client.getQueueData(method=category)
        if jobs:
            for job in jobs:
                client.deleteJob(job.job_id)
    else:
        client.deleteJob(job_id)
    return redirect(url_for("data.jobs"))
    


################################################################
# Rerunning a job
################################################################
#
# A job records the call that produced it: payload["params"] is a JSON object of the
# arguments the backend method was called with, keyed by position ("0", "1", ...) for
# the positional ones and by name for the rest - see mcrit's QueueRemoteCalls. That is
# enough to submit the same request again, but only where "the same request" is still
# a well-defined thing to ask for, so the mapping below is deliberately short:
#
#   * the query methods (getMatchesForSmdaReport and the two binary ones) are left out
#     because the binary they matched lives in the backend's GridFS. The job holds a
#     reference to it, not the bytes, and McritClient cannot resubmit from a reference.
#   * getUniqueBlocks is left out because neither of its request methods takes
#     force_recalculation, so repeating one is answered from the cache with the very
#     job being looked at.
#   * the collection and minhashing methods are left out because they are not analyses
#     to repeat - deleteSample and deleteFamily destroy, addBinarySample has no binary
#     to resend, and the maintenance jobs have their own buttons on the admin page.
#
# Reconstructing the wrong request would be worse than offering no button: the user
# would believe they had rerun what is on screen. So every step below refuses rather
# than guesses, and a parameter that cannot be read disqualifies the whole rerun
# instead of being dropped from it.

#: job method -> the McritClient method that submits it again.
RERUNNABLE_METHODS = {
    "getMatchesForSample": "requestMatchesForSample",
    "getMatchesForSampleVs": "requestMatchesForSampleVs",
    "combineMatchesToCross": "requestMatchesCross",
}

#: The matching parameters mcrit stores on a job under their own name; McritClient
#: takes them back as keywords of the same name. force_recalculation is deliberately
#: not among them - QueueRemoteCalls consumes it before the payload is written, so no
#: job records whether it was forced.
RERUN_MATCHING_PARAMS = ("minhash_threshold", "pichash_size", "band_matches_required")

#: The two child methods a cross compare is built from, and what each one means for
#: `sample_group_only` - the only place that choice survives.
CROSS_CHILD_METHODS = {"getMatchesForSample": False, "getMatchesForSampleVsGroup": True}

#: How many positional arguments each of those backend methods takes, so that a
#: payload carrying one this does not know about can be recognised as such. Together
#: with RERUN_MATCHING_PARAMS this is the complete parameter list of each method as of
#: mcrit 1.5 - a version that records a further one has to be handled here, and until
#: it is, the rerun is withheld rather than submitted without it.
METHOD_ARITY = {
    "getMatchesForSample": 1,
    "getMatchesForSampleVs": 2,
    "getMatchesForSampleVsGroup": 2,
    "combineMatchesToCross": 1,
}


def job_params(job_info):
    """A job's own parameters as {index_or_name: value}, or None if unreadable.

    `Job.arguments` parses the same payload but raises on anything that is not the
    JSON object it expects, and deciding whether to offer a rerun must not be able to
    take the job page down.
    """
    try:
        payload = job_info.payload
    except (AttributeError, KeyError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        params = json.loads(payload.get("params", ""))
    except (TypeError, ValueError):
        return None
    return params if isinstance(params, dict) else None


def as_job_int(value):
    """An integer parameter, or None. A bool is an int in Python and never one of these."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def matching_kwargs(params, method):
    """The named matching parameters of a job, or None if they cannot all be honoured.

    Unreadable is one way to get None; the other is a parameter this does not know
    about, positional or named. Both would otherwise be quietly left out of the
    resubmitted call, which is how a rerun ends up being a *different* comparison than
    the one on screen - so either disqualifies the job instead.
    """
    known = set(RERUN_MATCHING_PARAMS) | {str(position) for position in range(METHOD_ARITY[method])}
    if set(params) - known:
        return None
    kwargs = {}
    for name in RERUN_MATCHING_PARAMS:
        if name in params:
            value = as_job_int(params[name])
            if value is None:
                return None
            kwargs[name] = value
    return kwargs


def cross_rerun_request(params, child_jobs):
    """The requestMatchesCross call behind a combineMatchesToCross job, or None.

    That job records only {sample_id: child_job_id}. Which comparison ran is the
    choice between the two child methods, and the matching parameters exist only on
    the children - so a rerun is offered exactly when every child named in the mapping
    is still there and they all agree.
    """
    # this method takes the mapping and nothing else, so anything further in the
    # payload is a parameter that would be lost on the way back out
    if set(params) != {"0"}:
        return None
    sample_to_job_id = params["0"]
    if not isinstance(sample_to_job_id, dict) or not sample_to_job_id:
        return None
    children_by_id = {}
    for child in child_jobs or []:
        try:
            children_by_id[child.job_id] = child
        except (AttributeError, KeyError, TypeError):
            continue
    sample_ids = []
    methods = set()
    child_kwargs = []
    for sample_key, child_job_id in sample_to_job_id.items():
        try:
            sample_ids.append(int(sample_key))
        except (TypeError, ValueError):
            return None
        child = children_by_id.get(child_job_id)
        child_params = job_params(child) if child is not None else None
        if child_params is None or child.method not in CROSS_CHILD_METHODS:
            return None
        methods.add(child.method)
        kwargs = matching_kwargs(child_params, child.method)
        if kwargs is None:
            return None
        child_kwargs.append(kwargs)
    if len(methods) != 1 or any(kwargs != child_kwargs[0] for kwargs in child_kwargs):
        return None
    sample_group_only = CROSS_CHILD_METHODS[methods.pop()]
    return RERUNNABLE_METHODS["combineMatchesToCross"], (sample_ids,), dict(child_kwargs[0], sample_group_only=sample_group_only)


def rerun_request(job_info, child_jobs=None):
    """The McritClient call that reproduces `job_info`, as (method_name, args, kwargs).

    None means this job has no rerun: either its method is not one of the three above,
    or its stored parameters do not describe the original request completely.
    """
    if job_info is None:
        return None
    params = job_params(job_info)
    if params is None or job_info.method not in RERUNNABLE_METHODS:
        return None
    if job_info.method == "combineMatchesToCross":
        return cross_rerun_request(params, child_jobs)
    kwargs = matching_kwargs(params, job_info.method)
    if kwargs is None:
        return None
    sample_ids = [as_job_int(params.get(str(position))) for position in range(METHOD_ARITY[job_info.method])]
    if any(sample_id is None for sample_id in sample_ids):
        return None
    return RERUNNABLE_METHODS[job_info.method], tuple(sample_ids), kwargs


def has_run_its_course(job_info):
    """Whether a job is finished or failed, as opposed to queued or in progress.

    Forcing a recalculation of a job that is still running queues the same work a
    second time, so this gates both the button and the route that button posts to.
    Withholding the button alone would only hide the door - the POST is reachable
    without it.
    """
    if job_info is None:
        return False
    try:
        return job_info.finished_at is not None or bool(job_info.is_failed)
    except (AttributeError, KeyError, TypeError):
        # a record that does not carry the fields is not one to rerun either
        return False


def is_rerunnable(job_info, child_jobs=None):
    """Whether to offer a rerun of this job on its page."""
    if not has_run_its_course(job_info):
        return False
    return rerun_request(job_info, child_jobs) is not None


def configuration_url(job_info, child_jobs=None):
    """The analyze page this job was submitted from, with its inputs filled in.

    Issue #55's other half: from a finished job back to the form behind it, so the
    parameters can be changed and the job resubmitted rather than retyped. Built on
    `rerun_request` so there is one recovery of a job's arguments and not two - a job
    whose request cannot be rebuilt faithfully gets no link here either.

    Preselecting is not the same as passing the ids along. `analyze.compare` and
    `analyze.compare_versus` highlight a row only when the sample is on the search
    page in front of them, and compare.html falls back to selecting the *first* row
    when it is not - so a bare `selected=` would quietly point the form at a
    different sample. Each link therefore also carries the search that puts the
    sample on the page: searching a sample id makes mcrit answer with that sample
    (`id_match`), regardless of where it would otherwise fall in the paging.

    None means no link at all, which is the honest answer whenever the form cannot
    represent the job it claims to be showing.

    Not gated on the job having finished, unlike the rerun: following a link queues
    nothing, and reopening the form of a job still in the queue to submit a variation
    of it is a reasonable thing to want.
    """
    request_to_repeat = rerun_request(job_info, child_jobs)
    if request_to_repeat is None:
        return None
    method_name, args, kwargs = request_to_repeat
    kwargs = dict(kwargs)
    sample_group_only = kwargs.pop("sample_group_only", False)
    # `band_matches_required` is the only matching parameter these forms have a
    # control for. A job carrying another one cannot be shown on them, and one
    # carrying none took the backend's own default rather than a slider position,
    # which the slider - which always submits one - cannot reproduce either.
    if set(kwargs) != {"band_matches_required"}:
        return None
    slider_position = slider_position_for_band_range(kwargs["band_matches_required"])
    if slider_position is None:
        return None
    # `rematch` is left at each page's default: force_recalculation is consumed by
    # QueueRemoteCalls before the payload is written, so no job records whether it
    # was forced and preselecting either way would be an invention.
    if method_name == "requestMatchesCross":
        return url_for('analyze.cross_compare', samples=",".join(str(sample_id) for sample_id in args[0]),
                       onlySelected="true" if sample_group_only else "false", minhashBandRange=slider_position)
    if method_name == "requestMatchesForSample":
        return url_for('analyze.compare', query=args[0], selected=args[0], minhashBandRange=slider_position)
    if method_name == "requestMatchesForSampleVs":
        return url_for('analyze.compare_versus', query_a=args[0], selected_a=args[0],
                       query_b=args[1], selected_b=args[1], minhashBandRange=slider_position)
    # a method added to RERUNNABLE_METHODS has to say which form preselects it, and
    # how, before it can be linked to one
    return None


@bp.route('/jobs/<job_id>/rerun', methods=('POST',))
@visitor_required
@mcrit_server_required
def rerun_job_by_id(job_id):
    """Submit the request a job was created from once more.

    POST only, like every other route that changes something: this queues backend work
    and an <img> tag or a prefetch must not be able to start it (issue #84).

    Visitor, because it grants nothing a visitor does not already have - the same three
    requests are reachable from /analyze/compare/<id>, /analyze/compare/<a>/<b> and
    /analyze/start_cross_compare, `rematch` included.

    Nothing from the request is forwarded to the backend except `job_id` itself, which
    goes to the same getJobData that `job_by_id` already calls for any visitor. What is
    submitted is rebuilt here from the stored job, not from anything the caller sent.
    """
    client = get_client()
    job_info = client.getJobData(job_id)
    if job_info is None:
        flash('There is no job with that id.', category='error')
        return redirect(url_for('data.jobs'))
    if not has_run_its_course(job_info):
        # the button is withheld for a job that is still running, but withholding it
        # only hides the door: this POST is reachable without it, and forcing a
        # recalculation here would queue the same work alongside the run in progress
        flash('This job has not finished yet - wait for it rather than running it twice.', category='error')
        return redirect(url_for('data.job_by_id', job_id=job_id))
    child_jobs = None
    if job_info.method == "combineMatchesToCross":
        # only this one method needs them, so the round trips are not spent on the
        # other two. `all_dependencies` is a bare lookup in mcrit's Job and raises for
        # a record that does not carry the field.
        try:
            dependencies = job_info.all_dependencies
        except (KeyError, TypeError):
            dependencies = None
        child_jobs = [client.getJobData(child_id) for child_id in dependencies] if isinstance(dependencies, list) else []
    request_to_repeat = rerun_request(job_info, child_jobs)
    if request_to_repeat is None:
        flash('This job cannot be rerun: its original request is not fully recorded.', category='error')
        return redirect(url_for('data.job_by_id', job_id=job_id))
    method_name, args, kwargs = request_to_repeat
    # Forced, or mcrit answers from its descriptor cache with the job we started from
    # and the rerun is indistinguishable from a reload. This is the deliberate opposite
    # of the analyze routes, which must stay cacheable because they write on GET (#97).
    new_job_id = getattr(client, method_name)(*args, force_recalculation=True, **kwargs)
    if not new_job_id:
        flash('The backend did not accept the rerun; the samples it needs may be gone.', category='error')
        return redirect(url_for('data.job_by_id', job_id=job_id))
    return redirect(url_for('data.job_by_id', job_id=new_job_id, refresh=3))


################################################################
# Binary submission
################################################################

@bp.route('/request_filename_info', methods=['POST'])
@contributor_required
@mcrit_server_required
def request_filename_info():
    try:
        data_as_dict = json.loads(request.data)
        filename = data_as_dict["filename"]
        # the prefix carries base_addr and bitness; family and version only ever turn up
        # in the second window the client cuts around "metadata" (see dropzone.js).
        # .get so a client that predates that field still behaves exactly as before
        file_header = data_as_dict["file_header"] + data_as_dict.get("file_metadata", "")
    except Exception:
        filename = ""
        file_header = ""
    result = {}
    if filename.endswith(".smda"):
        result = {
            "smda": True,
            "family": None,
            "version": None,
            "bitness": None,
            "base_addr": None,
        }
        # parse from smda report
        match_family = re.search(r'"family": "(?P<family>[^"^<^>]+)"', file_header)
        if match_family:
            result['family'] = match_family.group('family')
        match_version = re.search(r'"version": "(?P<version>[^"^<^>]+)"', file_header)
        if match_version:
            result['version'] = match_version.group('version')
        match_bitness = re.search('"bitness": (?P<bitness>(16|32|64))', file_header)
        if match_bitness:
            result['bitness'] = int(match_bitness.group('bitness'))
        match_baseaddr = re.search(r'"base_addr": (?P<base_addr>\d+)', file_header)
        if match_baseaddr:
            result['base_addr'] = hex(int(match_baseaddr.group('base_addr')))
    elif 'dump' in filename:
        result['dump'] = True
        result['bitness'] = parseBitnessFromFilename(filename)
        base_address = parseBaseAddrFromFilename(filename)
        result['base_addr'] = "" if not base_address else hex(base_address)
    else:
        result['dump'] = False
    return json.dumps(result), 200


@bp.route('/submit_or_query', methods=('POST',))
@contributor_required
@mcrit_server_required
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
@contributor_required
@mcrit_server_required
def submit():
    client = get_client()
    if request.method == 'POST':
        f = request.files.get('file')
        if f is None:
            flash("Please upload a file", category='error')
            return "", 400 # Bad Request
        family = request.form['family']
        version = request.form['version']
        bitness = None
        base_address = None
        form_options = request.form['options']
        is_dump = form_options == "dumped"
        is_dump_or_smda = form_options in ['dumped', 'smda']
        if is_dump_or_smda:
            bitness = int(request.form['bitness'])
            base_address = int(request.form['base_addr'], 16)

        binary_content = f.read()
        if form_options == "smda":
            content_as_dict = json.loads(binary_content)
            smda_report = SmdaReport.fromDict(content_as_dict)
            upload_sha256 = smda_report.sha256
        else:
            # check here if it is already part of corpus
            upload_sha256 = hashlib.sha256(binary_content).hexdigest()
        sample_entry = client.getSampleBySha256(upload_sha256)
        if sample_entry is None:
            if form_options == "smda" and smda_report:
                new_sample_entry, job_id = client.addReport(smda_report)
                return url_for('explore.sample_by_id', sample_id=new_sample_entry.sample_id), 202 # Accepted
            else:
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
