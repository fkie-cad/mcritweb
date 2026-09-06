import time

from flask import Blueprint, flash, redirect, render_template, request, url_for
from mcrit.queue.JobCollection import JobCollection
from mcrit.storage.FamilyEntry import FamilyEntry
from mcrit.storage.FunctionEntry import FunctionEntry
from mcrit.storage.SampleEntry import SampleEntry

import mcritweb.views.cfg_explorer_detector as cfg_explorer_detector
from mcritweb.views.authentication import contributor_required, visitor_required
from mcritweb.views.client import get_client
from mcritweb.views.cursor_pagination import CursorPagination
from mcritweb.views.utility import get_user_column_setup, mcrit_server_required

bp = Blueprint('explore', __name__, url_prefix='/explore')

#: The queue methods a sample listing can show. `table/sample_row.html` asks the
#: collection for `matching_only=True` and for `method="getMatchesForSample"`, and
#: `Job.has_sample_id` answers only for the methods that carry a sample id as an
#: argument - so of the matching methods even `combineMatchesToCross` never reaches a
#: row. Everything else in the queue used to be fetched, deserialised into a `Job` and
#: dropped again on every listing view. mcrit's `/jobs` takes one method per request
#: and applies it as a mongo query *before* start/limit, so naming them costs two
#: requests and leaves submissions, minhashing and block jobs on the server. See #77.
SAMPLE_ROW_JOB_METHODS = ("getMatchesForSample", "getMatchesForSampleVs")

#: How many names `family_names` offers a type-ahead. The widget shows five of them;
#: the slack is there so a prefix with near-duplicates still reaches five.
FAMILY_NAME_SUGGESTIONS = 10

#: What `/explore/search` searches when the caller named nothing. See `search()`.
DEFAULT_SEARCH_TYPES = ["family", "sample"]


def sample_row_job_collection(client, samples):
    """The jobs a sample listing annotates its rows with.

    `filterToSampleIds` is what makes the result exact: it keeps only jobs whose own
    `sample_id` - their first argument - is on the page, which is the same set the row
    macro would have found in a collection built from the whole queue. An empty page
    has nothing to annotate, so it asks the backend for nothing.

    A failed queue read used to take the whole page down (`JobCollection(None)`), so
    say what was lost and render the rows without their annotations instead.

    All or nothing across the two requests. Keeping the half that answered would
    render badges that count some of a sample's matching jobs and not others, and the
    "Last 1:N Job" link comes from only one of the two methods - so a partial result
    is not a smaller true answer, it is a wrong one, shown with no indication that it
    is wrong. An empty collection at least matches what the message says.

    Concatenating the per-method answers would leave the result newest-first only
    *within* a method, so the merge is sorted back into one order. `Job.number` is the
    queue's own submission counter - `MongoQueue.put` takes it from a mongo counter,
    `LocalQueue.put` from an instance one - so descending `number` is the newest-first
    order an unqualified `getQueueData()` answered in. A job old enough to predate the
    counter carries no number, which `Job.number` reports as -1; those sort last, as
    the oldest, and python's stable sort leaves them in the order the backend listed
    them.
    """
    if not samples:
        return JobCollection([])
    jobs = []
    for method in SAMPLE_ROW_JOB_METHODS:
        jobs_for_method = client.getQueueData(method=method)
        if jobs_for_method is None:
            flash("Ups, reading MCRIT's job queue failed - rows are shown without their job annotations.", category="error")
            return JobCollection([])
        jobs.extend(jobs_for_method)
    jobs.sort(key=lambda job: job.number if isinstance(job.number, int) else -1, reverse=True)
    job_collection = JobCollection(jobs)
    job_collection.filterToSampleIds([sample.sample_id for sample in samples])
    return job_collection


##############################################################
### Unfiltered Collections: Families, Samples, Function
##############################################################

@bp.route('/modifyFamily', methods=['POST'])
@contributor_required
@mcrit_server_required
def modifyFamily():
    if request.method=='POST':
        data = request.data
        data = data.decode("utf-8")
        if not request.form.to_dict(flat=False):
            # returning None from a view is a TypeError inside Flask, so an empty
            # form submission answered with a 500 rather than saying what was wrong
            flash("Nothing to change - the form arrived empty.", category="error")
            return redirect(url_for('explore.families'))
        client = get_client()
        family_id = request.form.get("family_id", None)
        if family_id is None: 
            flash("No valid family_id received.", category="error")
            return redirect(url_for('explore.families'))
        family_entry = None
        try:
            family_id = int(family_id)
            family_entry = client.getFamily(family_id)
            if family_entry is None:
                raise ValueError
        except Exception:
            flash("No valid family_id received.", category="error")
            return redirect(url_for('explore.families'))
        # check if we want ot keep samples
        is_family_keeping_samples = True if request.form.get("family_keeping_samples", None) is not None else False
        is_family_delete = True if request.form.get("family_delete", None) is not None else False
        # delete family
        if is_family_delete:
            job_id = client.deleteFamily(family_id, keep_samples=is_family_keeping_samples)
            flash("Job to delete family was scheduled.", category="info")
            return redirect(url_for('data.job_by_id', job_id=job_id, refresh=5))
        # check if sample_entry should be modified
        new_family_name = request.form.get("family_new_name", None)
        new_is_library = True if request.form.get("family_is_library", None) is not None else False
        if new_family_name is None or new_family_name == family_entry.family:
            new_family_name = None
        if new_is_library is None or new_is_library == family_entry.is_library:
            new_is_library = None
        if any([item is not None for item in [new_family_name, new_is_library]]):
            job_id = client.modifyFamily(family_id, family_name=new_family_name, is_library=new_is_library)
            time.sleep(0.3)
        flash("Job to modify family was scheduled.", category="info")
    return redirect(url_for('explore.families'))

@bp.route('/familyNames')
@visitor_required
@mcrit_server_required
def family_names():
    """Names for the family type-ahead in the edit modals, as JSON.

    Every page carrying one of those modals used to embed the complete list of family
    names in its source. mcrit answers `getFamilies()` with one storage lookup per
    family (`MinHashIndex.getFamilies`), so a listing paid for the whole family table
    on every view whether or not anyone opened a modal, and the cost grew with the
    corpus. A prefix needs a handful of names, and `search_families` is the bounded way
    to ask for them. Visitors already read every family name off `/explore/families`,
    so this exposes nothing new. See issue #77.

    A backend that cannot answer costs the suggestions, not the modal - the field is a
    free-text input and stays usable without them.
    """
    query = request.args.get('q', "")
    client = get_client()
    results = client.search_families(query, limit=FAMILY_NAME_SUGGESTIONS)
    if results is None:
        return {"family_names": []}
    return {"family_names": [FamilyEntry.fromDict(entry).family_name for entry in results['search_results'].values()]}


@bp.route('/families')
@visitor_required
@mcrit_server_required
def families():
    family_id = request.args.get('family_id')
    if family_id is not None:
        return redirect(url_for('explore.family_by_id', family_id=family_id, p=request.args.get('p')))
    query = request.args.get('query', "")
    client = get_client()
    families = []
    pagination = CursorPagination(request, default_sort="family_id", limit=25)
    results = client.search_families(query, **pagination.getSearchParams(), limit=pagination.limit)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's families failed!", category="error")
    else:
        for family_dict in results['search_results'].values():
            families.append(FamilyEntry.fromDict(family_dict))
    user_column_setup = get_user_column_setup("family_table")
    return render_template("families.html", families=families, pagination=pagination, query=query, user_column_setup=user_column_setup)

@bp.route('/modifySample', methods=['POST'])
@contributor_required
@mcrit_server_required
def modifySample():
    if request.method=='POST':
        data = request.data
        data = data.decode("utf-8")
        if not request.form.to_dict(flat=False):
            flash("Nothing to change - the form arrived empty.", category="error")
            return redirect(url_for('explore.samples'))
        client = get_client()
        sample_id = request.form.get("sample_id", None)
        redirection_job_id = request.form.get("redirection_job_id", None)
        if redirection_job_id is not None and client.getJobData(redirection_job_id) is None: 
            flash("Trying to redirect from invalid job_Id.", category="error")
            return redirect(url_for('explore.samples'))
        sample_entry = None
        if sample_id is None: 
            flash("No valid sample_id received.", category="error")
            return redirect(url_for('explore.samples'))
        sample_entry = None
        try:
            sample_id = int(sample_id)
            sample_entry = client.getSampleById(sample_id)
            if sample_entry is None:
                raise ValueError
        except Exception:
            flash("No valid sample_id received.", category="error")
            return redirect(url_for('explore.samples'))
        is_sample_delete = True if request.form.get("sample_delete", None) is not None else False
        # delete sample
        if is_sample_delete:
            job_id = client.deleteSample(sample_id)
            flash("Job to delete sample was scheduled.", category="info")
            return redirect(url_for('data.job_by_id', job_id=job_id, refresh=5))
        # check if sample_entry should be modified
        new_family_name = request.form.get("sample_family_name", None)
        new_version = request.form.get("sample_version", None)
        new_is_library = True if request.form.get("sample_is_library", None) is not None else False
        if new_family_name is None or new_family_name == sample_entry.family:
            new_family_name = None
        if new_version is None or new_version == sample_entry.version:
            new_version = None
        if new_is_library is None or new_is_library == sample_entry.is_library:
            new_is_library = None
        if any([item is not None for item in [new_family_name, new_version, new_is_library]]):
            client.modifySample(sample_id, family_name=new_family_name, version=new_version, is_library=new_is_library)
            time.sleep(0.3)
        if redirection_job_id:
            time.sleep(1)
            flash("Delayed redirect for 1 second to let requested sample modification propagate", category="info")
            return redirect(url_for('data.result', job_id=redirection_job_id))
        flash("Job to modify sample was scheduled.", category="info")
    return redirect(url_for('explore.samples'))


@bp.route('/samples')
@visitor_required
@mcrit_server_required
def samples():
    sample_id = request.args.get('sample_id')
    if sample_id is not None:
        return redirect(url_for('explore.sample_by_id', sample_id=sample_id, p=request.args.get('p')))

    query = request.args.get('query', "")
    client = get_client()
    samples = []
    pagination = CursorPagination(request, default_sort="sample_id", limit=25)
    results = client.search_samples(query, **pagination.getSearchParams(), limit=pagination.limit)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
    else:
        for sample_dict in results['search_results'].values():
            samples.append(SampleEntry.fromDict(sample_dict))

    job_collection = sample_row_job_collection(client, samples)

    user_column_setup = get_user_column_setup("samples_table")
    return render_template("samples.html", samples=samples, job_collection=job_collection, pagination=pagination, query=query, user_column_setup=user_column_setup)


@bp.route('/functions')
@visitor_required
@mcrit_server_required
def functions():
    function_id = request.args.get('function_id')
    if function_id is not None:
        return redirect(url_for('explore.function_by_id', function_id=function_id, p=request.args.get('p')))
    query = request.args.get('query', "")
    client = get_client()
    functions = []
    pagination = CursorPagination(request, default_sort="function_id", limit=25)
    results = client.search_functions(query, **pagination.getSearchParams(), limit=pagination.limit)
    pagination.read_cursor_from_result(results)
    if results is None:
        flash(f"Ups, search for {query} in MCRIT's functions failed!", category="error")
    else:
        for function_dict in results['search_results'].values():
            #functions.append(FunctionEntry.fromDict(function_dict))
            functions.append(function_dict)
    user_column_setup = get_user_column_setup("functions_table")
    return render_template("functions.html", functions=functions, pagination=pagination, query=query, user_column_setup=user_column_setup)

##############################################################
### Single Entries: Families, Samples, Function
##############################################################

@bp.route('/families/<int:family_id>')
@visitor_required
@mcrit_server_required
def family_by_id(family_id):
    client = get_client()
    family_info = client.getFamily(family_id, with_samples=False)
    if family_info:
        original_query = request.args.get('query', "")
        query = f"family_id:{family_id} {original_query}"
        client = get_client()
        samples = []
        pagination = CursorPagination(request, default_sort="sample_id", limit=25)
        results = client.search_samples(query, **pagination.getSearchParams(), limit=pagination.limit)
        pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
        else:
            for sample_dict in results['search_results'].values():
                samples.append(SampleEntry.fromDict(sample_dict))
        job_collection = sample_row_job_collection(client, samples)
        user_column_setup = get_user_column_setup("samples_table")
        return render_template("single_family.html", family=family_info, samples=samples, job_collection=job_collection, pagination=pagination, query=original_query, user_column_setup=user_column_setup)
    else:
        flash("The given Family ID doesn't exist", category='error')
        return redirect(url_for('explore.families'))


@bp.route('/samples/<int(signed=True):sample_id>')
@visitor_required
@mcrit_server_required
def sample_by_id(sample_id):
    client = get_client()
    sample_entry = client.getSampleById(sample_id)
    if sample_entry:
        if sample_id < 0:
            return render_template("single_query_sample.html", entry=sample_entry)
        original_query = request.args.get('query', "")
        query = f"sample_id:{sample_id} {original_query}"
        functions = []
        # bound up front: the job table below is read outside the branch that fills it,
        # and a failed function search left the name undefined - a 500 on the page that
        # was meant to report the failure. A failed queue read is the same story one
        # level down, since `JobCollection(None)` is only a TypeError waiting to happen.
        job_collection = JobCollection([])
        pagination = CursorPagination(request, default_sort="function_id", limit=100)
        results = client.search_functions(query, **pagination.getSearchParams(), limit=pagination.limit)
        pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's functions failed!", category="error")
        else:
            # `McritClient.getQueueData` only forwards a `filter` that is a str, so
            # this used to be dropped on the floor and the whole queue came back. The
            # server matches it as a substring of the job's `method(args...)` string
            # *after* paging (`QueueRemoteCalls.getQueueData`), which is unusable with
            # a `limit` - but there is none here, and every job whose own `sample_id`
            # is this one renders that id into its parameters, so the narrowed set is
            # a superset of what `filterToSampleIds` keeps below. See #77.
            jobs = client.getQueueData(filter=str(sample_id))
            if jobs is None:
                flash("Ups, reading MCRIT's job queue failed - this sample's jobs are not shown.", category="error")
            else:
                job_collection = JobCollection(jobs)
                job_collection.filterToSampleIds([sample_id])
            for function_dict in results['search_results'].values():
                functions.append(FunctionEntry.fromDict(function_dict))
        samples_by_id = {}
        for job in job_collection.getJobs():
            if job.sample_ids is not None:
                for sample_id in [sid for sid in job.sample_ids if sid not in samples_by_id]:
                    samples_by_id[sample_id] = client.getSampleById(sample_id)
        user_column_setup = get_user_column_setup("functions_table")
        return render_template("single_sample.html", entry=sample_entry, functions=functions, pagination=pagination, query=original_query, samples=samples_by_id, job_collection=job_collection, user_column_setup=user_column_setup)
    else:
        flash("The given Sample ID doesn't exist", category='error')
        return redirect(url_for('explore.samples'))


@bp.route('/functions/<int(signed=True):function_id>')
@visitor_required
@mcrit_server_required
def function_by_id(function_id):
    client = get_client()
    function_entry = client.getFunctionById(function_id)
    if function_entry:
        sample_entry = client.getSampleById(function_entry.sample_id)
        pichash_match_summary = client.getMatchesForPicHash(function_entry.pichash, summary=True)
        return render_template("single_function.html", entry=function_entry, sample_entry=sample_entry, pichash_match_summary=pichash_match_summary)
    else:
        flash("The given Function ID doesn't exist", category="error")
        return redirect(url_for('explore.functions'))

# helper for @bp.route('/functions/<int:function_id>')
@bp.route('/fetchDotGraph/<int(signed=True):function_id>', methods=['GET'])
@visitor_required
@mcrit_server_required
def fetchDotGraph(function_id):
    client = get_client()
    function_entry = client.getFunctionById(function_id, with_xcfg=True)
    if function_entry:
        smda_function = function_entry.toSmdaFunction()
        dot_graph = smda_function.toDotGraph(with_api=True)
        # TODO can possibly do this fixup in a better place
        pbh_by_offset = {pbh["offset"]: pbh for pbh in function_entry.picblockhashes}
        for smda_block in smda_function.getBlocks():
            needle = f',label="{smda_block.offset:x}'
            replacement = f',comment=""{needle}'
            if smda_block.offset in pbh_by_offset:
                replacement = f',comment="0x{pbh_by_offset[smda_block.offset]["hash"]:x}"{needle}'
            dot_graph = dot_graph.replace(needle, replacement)
        return dot_graph
    return ""

# helper for @bp.route('/functions/<int:function_id>')
@bp.route('/findLoops/', methods=['GET', 'POST'])
@visitor_required
@mcrit_server_required
def findLoops():
    out_str = ""
    if request.method=='POST':
        data = request.data
        data = data.decode("utf-8")
        out_str = cfg_explorer_detector.run(data)
    return out_str


# helper for @bp.route('/functions/<int:function_id>')
@bp.route('/getPicBlockMatches/<picblockhash>', methods=['GET'])
@visitor_required
@mcrit_server_required
def getPicBlockMatches(picblockhash):
    client = get_client()
    return client.getMatchesForPicBlockHash(int(picblockhash, 16), summary=True)

##############################################################
### Statistics + Search
##############################################################

@bp.route('/statistics')
@visitor_required
@mcrit_server_required
def statistics():
    client = get_client()
    stats = client.getStatus()
    return render_template("statistics.html", stats=stats)


@bp.route('/search')
@visitor_required
@mcrit_server_required
def search():
    query = request.args.get('query', None)
    types = request.args.getlist("type")
    if len(types) > 1:
        args = {**request.args}
        args["type"] = ",".join(types)
        return redirect(url_for("explore.search", **args))
    if "type" not in request.args:
        # Functions are deliberately not in the default. A function search scans the
        # whole function collection and takes ~30 seconds on a large instance when it
        # finds nothing (issue #76), and running it unasked charged that to every
        # search from the navbar and to every pagination click on the other two
        # tables. It is one tick away, and search.html says so where the function
        # results would have been - this narrows who pays for the scan, it does not
        # make the scan faster. That part is mcrit's.
        types = list(DEFAULT_SEARCH_TYPES)
    else:
        types = request.args["type"].split(",")
    if not query:
        return render_template("search.html", search_types=types)
    client = get_client()

    #TODO: show id/sha matches in extra place
    families = []
    family_pagination = None
    if 'family' in types:
        family_pagination = CursorPagination(request, query_param_prefix="family", default_sort="family_id", limit=25)
        results = client.search_families(query, **family_pagination.getSearchParams(), limit=family_pagination.limit)
        family_pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's families failed!", category="error")
        else:
            id_match = results['id_match']
            if id_match is not None:
                family = FamilyEntry.fromDict(id_match)
                families.append(family)
            for family_entry in results['search_results'].values():
                family = FamilyEntry.fromDict(family_entry)
                families.append(family) 

    samples = {}
    sample_pagination = None
    if 'sample' in types:
        sample_pagination = CursorPagination(request, query_param_prefix="sample", default_sort="sample_id", limit=25)
        results = client.search_samples(query, **sample_pagination.getSearchParams(), limit=sample_pagination.limit)
        sample_pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's samples failed!", category="error")
        else:
            sha_match = results['sha_match']
            if sha_match is not None:
                sample_entry = SampleEntry.fromDict(sha_match)
                samples[sample_entry.sample_id] = sample_entry
            id_match = results['id_match']
            if id_match is not None:
                # both of these arrive as dicts off the wire, like sha_match above -
                # which is the one branch here that deserialises before reading a field
                sample_entry = SampleEntry.fromDict(id_match)
                samples[sample_entry.sample_id] = sample_entry
            for sample_dict in results['search_results'].values():
                sample_entry = SampleEntry.fromDict(sample_dict)
                samples[sample_entry.sample_id] = sample_entry
    # deduplicate in case we have cases such as filename == sha256
    samples = list(samples.values())

    functions = []
    function_pagination = None
    if 'function' in types:
        function_pagination = CursorPagination(request, query_param_prefix="function", default_sort="function_id", limit=25)
        results = client.search_functions(query, **function_pagination.getSearchParams(), limit=function_pagination.limit)
        function_pagination.read_cursor_from_result(results)
        if results is None:
            flash(f"Ups, search for {query} in MCRIT's functions failed!", category="error")
        else:
            id_match = results['id_match']
            if id_match is not None:
                functions.append(FunctionEntry.fromDict(id_match))
            for function_dict in results['search_results'].values():
                functions.append(FunctionEntry.fromDict(function_dict))

    family_column_setup = get_user_column_setup("family_table")
    sample_column_setup = get_user_column_setup("samples_table")
    function_column_setup = get_user_column_setup("functions_table")
    return render_template(
        "search.html",
        families=families,
        samples=samples,
        functions=functions,
        family_pagination=family_pagination,
        sample_pagination=sample_pagination,
        function_pagination=function_pagination,
        query=query,
        search_types=types,
        family_column_setup=family_column_setup,
        sample_column_setup=sample_column_setup,
        function_column_setup=function_column_setup
    )
