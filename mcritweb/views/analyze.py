import re
import os
from hashlib import sha256
from flask import Blueprint, render_template, request, redirect, session, url_for, current_app, json, flash
from mcrit.client.McritClient import McritClient
from mcrit.storage.SampleEntry import SampleEntry

from mcritweb.views.authentication import visitor_required, contributor_required
from mcritweb.views.utility import get_server_url, mcrit_server_required
from mcritweb.views.pagination import Pagination
from mcritweb.views.cursor_pagination import CursorPagination
from mcritweb.views.cross_compare import score_to_color

bp = Blueprint('analyze', __name__, url_prefix='/analyze')


@bp.route('/blocks/family/<int:family_id>')
@visitor_required
@mcrit_server_required
def blocks_family(family_id):
    client = McritClient(mcrit_server=get_server_url())
    job_id = client.getUniqueBlocksForFamily(family_id)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))

    if results is None:
        flash(f"Ups, no results for unique blocks in family with id {family_id}", category="error")
    
    number_of_unique_blocks = len(results)
    for pichash, result in results.items():
        yarafied = f"/* picblockhash: {pichash} \n"
        maxlen_ins = max([len(ins[1]) for ins in result["instructions"]])
        for ins in result["instructions"]:
            yarafied += f" * {ins[1]:{maxlen_ins}} | {ins[2]} {ins[3]}\n"
        yarafied += " */\n"
        
        yarafied += "{ " + re.sub("(.{80})", "\\1\n", result["escaped_sequence"], 0, re.DOTALL) + " }"
        results[pichash]["yarafied"] = yarafied

    return render_template(
        "blocks_family.html",
        family_id=family_id,
        number_of_unique_blocks=number_of_unique_blocks,
        results=results,
    )


@bp.route('/blocks/sample/<int:sample_id>')
@visitor_required
@mcrit_server_required
def blocks_sample(sample_id):
    client = McritClient(mcrit_server=get_server_url())
    job_id = client.getUniqueBlocksForSamples([sample_id])
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))

    if results is None:
        flash(f"Ups, no results for unique blocks in family with id {sample_id}", category="error")
    
    number_of_unique_blocks = len(results)
    for pichash, result in results.items():
        yarafied = f"/* picblockhash: {pichash} \n"
        maxlen_ins = max([len(ins[1]) for ins in result["instructions"]])
        for ins in result["instructions"]:
            yarafied += f" * {ins[1]:{maxlen_ins}} | {ins[2]} {ins[3]}\n"
        yarafied += " */\n"
        
        yarafied += "{ " + re.sub("(.{80})", "\\1\n", result["escaped_sequence"], 0, re.DOTALL) + " }"
        results[pichash]["yarafied"] = yarafied

    return render_template(
        "blocks_sample.html",
        sample_id=sample_id,
        number_of_unique_blocks=number_of_unique_blocks,
        results=results,
    )


@bp.route('/compare_submit_query')
@visitor_required
def compare_submit_query():
    return render_template("compare_submit_query.html")

@bp.route('/cross_compare', methods=['GET','POST'])
@visitor_required
@mcrit_server_required
def cross_compare():
    client = McritClient(mcrit_server= get_server_url())

    selected = request.args.get('samples', '').strip(',')
    cached = request.args.get('cache','').strip(',')
    is_forcing_rematch = True if request.args.get('rematch', 'true').lower() == "true" else False

    cached_list = [int(x) for x in cached.split(',') if x!='']
    selected_list = [int(x) for x in selected.split(',') if x != '']

    pagination_selected = Pagination(request, len(selected_list), limit=10, query_param="ps")
    selected_dict = {x: client.getSampleById(x) for x in sorted(selected_list)[pagination_selected.start_index:pagination_selected.start_index+pagination_selected.limit]}
    invalid_ids = []
    for id, sample in selected_dict.items():
        if sample is None:
            invalid_ids.append(id)
    for invalid_id in invalid_ids:
        forward = True
        selected_dict.pop(invalid_id)
        selected_list.remove(invalid_id)
        flash(f"Sample with Id {invalid_id} does not exist and was ignored", category="warning")

    if invalid_ids:
        return redirect(url_for(
            "analyze.cross_compare",
            samples = ",".join([str(id) for id in selected_list]),
            cache = ",".join([str(id) for id in cached_list]),
            rematch = "true" if is_forcing_rematch else "False",
        ))

    query = request.args.get('query', "")
    samples = []
    pagination = CursorPagination(request, default_sort="sample_id")
    results = client.search_samples(query, **pagination.getSearchParams(), limit=10)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
    else:
        for sample_dict in results['search_results'].values():
            samples.append(SampleEntry.fromDict(sample_dict))


    return render_template(
        "cross_compare.html",
        samples=samples,       # all / searched samples
        pagination=pagination, # all / searched samples
        selected_ids=selected_list,
        selected_samples=selected_dict.values(),
        pagination_selected=pagination_selected,
        cached=cached_list,
        is_forcing_rematch=is_forcing_rematch,
        query=query,
    )


@bp.route('/start_cross_compare')
@visitor_required
@mcrit_server_required
def start_cross_compare():
    client = McritClient(mcrit_server= get_server_url())
    selected = request.args.get('samples', '')
    rematch = request.args.get('rematch', '')
    if selected != '':
        selected_list = [int(x) for x in selected.split(',') if x != '']
        job_id = client.requestMatchesCross(selected_list, force_recalculation=rematch)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))


@bp.route('/compare')
@visitor_required
@mcrit_server_required
def compare():
    client = McritClient(mcrit_server= get_server_url())

    query = request.args.get('query', "")
    samples = []
    pagination = CursorPagination(request, default_sort="sample_id")
    results = client.search_samples(query, **pagination.getSearchParams(), limit=10)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
    else:
        for sample_dict in results['search_results'].values():
            samples.append(SampleEntry.fromDict(sample_dict))

    rematch = True if request.args.get('rematch', 'true').lower() == "true" else False
    return render_template(
        "compare.html",
        samples=samples,
        pagination=pagination,
        selected=request.args.get('selected', ""),
        rematch=rematch,
        query=query
    )


@bp.route('/compare_versus')
@visitor_required
@mcrit_server_required
def compare_versus():
    client = McritClient(mcrit_server= get_server_url())

    parameters = {}
    for a_or_b in "ab":
        query = request.args.get(f'query_{a_or_b}', "")
        samples = []
        pagination = CursorPagination(request, default_sort="sample_id", query_param_prefix=a_or_b)
        results = client.search_samples(query, **pagination.getSearchParams(), limit=10)
        pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
        else:
            for sample_dict in results['search_results'].values():
                samples.append(SampleEntry.fromDict(sample_dict))
        selected=request.args.get(f'selected_{a_or_b}', "")

        parameters[f"samples_{a_or_b}"] = samples
        parameters[f"pagination_{a_or_b}"] = pagination 
        parameters[f"selected_{a_or_b}"] = selected 
        parameters[f"query_{a_or_b}"] = query 

    parameters["rematch"] = True if request.args.get('rematch', 'true').lower() == "true" else False
    return render_template("compare_versus.html", **parameters)

@bp.route('/compare/<sample_id_a>')
@visitor_required
@mcrit_server_required
def compare_all(sample_id_a):
    client = McritClient(mcrit_server= get_server_url())
    rematch = request.args.get('rematch', False)
    job_id = client.requestMatchesForSample(sample_id_a, force_recalculation=rematch)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))

@bp.route('/compare/<sample_id_a>/<sample_id_b>')
@visitor_required
@mcrit_server_required
def compare_vs(sample_id_a, sample_id_b):
    client = McritClient(mcrit_server= get_server_url())
    rematch = request.args.get('rematch', False)
    job_id = client.requestMatchesForSampleVs(sample_id_a, sample_id_b, force_recalculation=rematch)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))

@bp.route('/query',methods=('GET', 'POST'))
@mcrit_server_required
@contributor_required
def query():
    client = McritClient(mcrit_server=get_server_url())
    if request.method == 'POST':
        f = request.files.get('file')
        if f is None:
            flash("Please upload a file", category='error')
            return "", 400 # Bad Request

        base_address = None
        is_dump = request.form['options'] == 'dumped'
        if is_dump:
            base_address = int(request.form['base_address'], 16)

        binary_content = f.read()
        if is_dump:
            job_id = client.requestMatchesForMappedBinary(binary=binary_content, disassemble_locally=False, base_address=base_address, force_recalculation=True)
        else:
            job_id = client.requestMatchesForUnmappedBinary(binary=binary_content, disassemble_locally=False, force_recalculation=True)
        
        if job_id is not None:
            flash('Sample submitted!', category='success')
            return url_for('data.job_by_id', job_id=job_id, refresh=3, forward=1), 202 # Accepted
        else:
            flash('Sample could not be disassembled!', category='error')
            return "", 400 # Bad Request
    return render_template('query.html', families=[], show_submit_fields=False)