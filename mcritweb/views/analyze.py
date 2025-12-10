import re
import os
import hashlib
from flask import Blueprint, g, render_template, request, redirect, session, url_for, current_app, json, flash
from mcrit.client.McritClient import McritClient
from mcrit.storage.SampleEntry import SampleEntry
from smda.common.SmdaReport import SmdaReport

from mcritweb.views.authentication import visitor_required, contributor_required
from mcritweb.views.utility import get_server_url, get_server_token, mcrit_server_required, get_username, parse_band_range
from mcritweb.views.pagination import Pagination
from mcritweb.views.cursor_pagination import CursorPagination
from mcritweb.views.cross_compare import score_to_color

bp = Blueprint('analyze', __name__, url_prefix='/analyze')


def get_unique_samples_from_search_result(search_result):
    samples = []
    sample_ids = set()
    for sample_dict in search_result['search_results'].values():
        sample_entry = SampleEntry.fromDict(sample_dict)
        if sample_entry.sample_id not in sample_ids:
            samples.append(sample_entry)
            sample_ids.add(sample_entry.sample_id)
    id_match = search_result['id_match']
    if id_match is not None and id_match["sample_id"] not in sample_ids:
        samples.append(SampleEntry.fromDict(id_match))
    return samples


@bp.route('/blocks/family/<int:family_id>')
@visitor_required
@mcrit_server_required
def blocks_family(family_id):
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    family_samples = client.getSamplesByFamilyId(family_id)
    if family_samples:
        job_id = client.requestUniqueBlocksForFamily(family_id)
        return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))
    else:
        flash("Can't locate unique blocks for a family without samples", category="error")
        return redirect(url_for('explore.families'))


@bp.route('/blocks/sample/<int:sample_id>')
@visitor_required
@mcrit_server_required
def blocks_sample(sample_id):
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    job_id = client.requestUniqueBlocksForSamples([sample_id])
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))


@bp.route('/compare_submit_query')
@visitor_required
def compare_submit_query():
    return render_template("compare_submit_query.html")

@bp.route('/cross_compare_from_hash_list', methods=['GET', 'POST'])
@visitor_required
@mcrit_server_required
def cross_compare_from_hash_list():
    client = McritClient(mcrit_server= get_server_url(), apitoken=get_server_token(), username=get_username())

    selected = ""
    cached = request.args.get('cache','').strip(',')
    cached_list = []
    selected_list = []
    is_forcing_rematch = True if request.args.get('rematch', 'false').lower() == "true" else False
    if request.method == 'POST':
        hash_list = request.form.get('hashlist', '').strip().splitlines()
        # sanitize to sha256 hashes
        sanitized_hashes = []
        for h in hash_list:
            h = h.strip()
            if re.match(r'^[a-fA-F0-9]{64}$', h):
                sanitized_hashes.append(h)
            else:
                flash(f"Hash '{h}' is not a valid SHA256 hash and was ignored", category="warning")
        if not sanitized_hashes:
            flash("No valid hashes provided", category="error")
            return redirect(url_for('analyze.cross_compare_from_hash_list'))
        # get sample ids from hashes
        selected_samples = []
        for h in sanitized_hashes:
            sample_entry = client.getSampleBySha256(h)
            if sample_entry is not None:
                selected_samples.append(sample_entry)
            else:
                flash(f"Hash '{h}' does not correspond to any sample in the database and was ignored", category="warning")
        if not selected_samples:
            flash("No valid samples found for the provided hashes", category="error")
            return redirect(url_for('analyze.cross_compare_from_hash_list'))
        # redirect to cross_compare with selected samples
        selected = ",".join([str(s.sample_id) for s in selected_samples])

        selected_list = [int(x) for x in selected.split(',') if x != '']


        # fill up search part with all samples
        samples = []
        pagination = CursorPagination(request, default_sort="sample_id")
        results = client.search_samples("", **pagination.getSearchParams(), limit=pagination.limit)
        pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
            
        # unused? -> pagination_selected = Pagination(request, len(selected_list), limit=25, query_param="ps")

        return redirect(url_for(
            "analyze.cross_compare",
            samples = ",".join([str(id) for id in selected_list]),
            cache = ",".join([str(id) for id in cached_list]),
            rematch = "true" if is_forcing_rematch else "false",
        ))
    else:
        return render_template("cross_compare_from_hash_list.html")

@bp.route('/cross_compare', methods=['GET','POST'])
@visitor_required
@mcrit_server_required
def cross_compare():
    client = McritClient(mcrit_server= get_server_url(), apitoken=get_server_token(), username=get_username())

    selected = request.args.get('samples', '').strip(',')
    cached = request.args.get('cache','').strip(',')
    is_forcing_rematch = True if request.args.get('rematch', 'false').lower() == "true" else False

    cached_list = [int(x) for x in cached.split(',') if x!='']
    selected_list = [int(x) for x in selected.split(',') if x != '']

    pagination_selected = Pagination(request, len(selected_list), limit=10, query_param="ps", limit_param="psl")
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
            rematch = "true" if is_forcing_rematch else "false",
        ))

    query = request.args.get('query', "")
    samples = []
    pagination = CursorPagination(request, default_sort="sample_id")
    results = client.search_samples(query, **pagination.getSearchParams(), limit=pagination.limit)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
    else:
        samples = get_unique_samples_from_search_result(results)

    return render_template(
        "cross_compare.html",
        samples=samples,       # all / searched samples
        pagination=pagination, # all / searched samples
        selected_ids=selected_list,
        selected_samples=selected_dict.values(),
        pagination_selected=pagination_selected,
        cached=cached_list,
        rematch=is_forcing_rematch,
        query=query,
    )


@bp.route('/start_cross_compare')
@visitor_required
@mcrit_server_required
def start_cross_compare():
    client = McritClient(mcrit_server= get_server_url(), apitoken=get_server_token(), username=get_username())
    selected = request.args.get('samples', '')
    rematch = request.args.get('rematch', '')
    minhash_band_range = parse_band_range(request)
    if selected != '':
        selected_list = [int(x) for x in selected.split(',') if x != '']
        job_id = client.requestMatchesCross(selected_list, force_recalculation=rematch, band_matches_required=minhash_band_range)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))


@bp.route('/compare')
@visitor_required
@mcrit_server_required
def compare():
    client = McritClient(mcrit_server= get_server_url(), apitoken=get_server_token(), username=get_username())

    query = request.args.get('query', "")
    samples = []
    pagination = CursorPagination(request, default_sort="sample_id")
    results = client.search_samples(query, **pagination.getSearchParams(), limit=pagination.limit)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
    else:
        samples = get_unique_samples_from_search_result(results)

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
    client = McritClient(mcrit_server= get_server_url(), apitoken=get_server_token(), username=get_username())

    parameters = {}
    for a_or_b in "ab":
        query = request.args.get(f'query_{a_or_b}', "")
        samples = {}
        pagination = CursorPagination(request, default_sort="sample_id", query_param_prefix=a_or_b)
        results = client.search_samples(query, **pagination.getSearchParams(), limit=pagination.limit)
        pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
        else:
            samples = get_unique_samples_from_search_result(results)
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
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    rematch = request.args.get('rematch', False)
    minhash_band_range = parse_band_range(request)
    job_id = client.requestMatchesForSample(sample_id_a, force_recalculation=rematch, band_matches_required=minhash_band_range)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))

@bp.route('/compare/<sample_id_a>/<sample_id_b>')
@visitor_required
@mcrit_server_required
def compare_vs(sample_id_a, sample_id_b):
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    rematch = request.args.get('rematch', False)
    minhash_band_range = parse_band_range(request)
    job_id = client.requestMatchesForSampleVs(sample_id_a, sample_id_b, force_recalculation=rematch, band_matches_required=minhash_band_range)
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))

@bp.route('/query',methods=('GET', 'POST'))
@mcrit_server_required
@visitor_required
def query():
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    if request.method == 'POST':
        f = request.files.get('file')
        if f is None:
            flash("Please upload a file", category='error')
            return "", 400 # Bad Request

        base_address = None
        form_options = request.form['options']
        is_dump_or_smda = form_options in ['dumped', 'smda']
        if is_dump_or_smda:
            bitness = int(request.form['bitness'])
            base_address = int(request.form['base_addr'], 16)

        binary_content = f.read()
        if g.user.role == 'visitor' and len(binary_content) > 1 * 2**20:
            flash(f'Your account may only upload files for query that are up to {1 * 2**20} bytes in size.', category='error')
            return "", 403 # Bad Request
        # persist the upload in binary format

        if form_options == "smda":
            content_as_dict = json.loads(binary_content)
            smda_report = SmdaReport.fromDict(content_as_dict)
            upload_sha256 = smda_report.sha256
        else:
            # check here if it is already part of corpus
            upload_sha256 = hashlib.sha256(binary_content).hexdigest()

        with open(os.sep.join([current_app.instance_path, "temp", "uploads", upload_sha256]), "wb") as fout:
            fout.write(binary_content)

        minhash_band_range = parse_band_range(request)
        if form_options == "smda":
            job_id = client.requestMatchesForSmdaReport(smda_report, force_recalculation=True, band_matches_required=minhash_band_range)
        elif form_options == "dumped":
            job_id = client.requestMatchesForMappedBinary(binary=binary_content, disassemble_locally=False, base_address=base_address, force_recalculation=True, band_matches_required=minhash_band_range)
        else:
            job_id = client.requestMatchesForUnmappedBinary(binary=binary_content, disassemble_locally=False, force_recalculation=True, band_matches_required=minhash_band_range)
        
        if job_id is not None:
            flash('Sample submitted!', category='success')
            return url_for('data.job_by_id', job_id=job_id, refresh=3, forward=1), 202 # Accepted
        else:
            flash('Sample could not be parsed / disassembled!', category='error')
            return "", 400 # Bad Request
    return render_template('query.html', families=[], show_submit_fields=False)
