import os
import re
import shutil
import struct
import hashlib
import logging 
import requests
import functools 

from flask import redirect, url_for, flash, session, g
from rapidfuzz.distance import Levenshtein
from smda.intel.IntelInstructionEscaper import IntelInstructionEscaper
from mcrit.client.McritClient import McritClient

from mcritweb import db


def get_server_url():
    database = db.get_db()
    return database.execute('SELECT * FROM server').fetchone()['url']


def set_server_url(new_url):
    database = db.get_db()
    database.execute("UPDATE server SET url = ?",(new_url,))
    database.commit()
    return


def mcrit_server_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        try:
            requests.get(f"{get_server_url()}/", headers={"username":"mcritweb"})
        except:
            flash('No connection to the Mcrit server', category='error')
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view


def get_session_user_id():
    try:
        user_id = int(session['user_id'])
        if user_id > 0:
            return user_id
    except:
        return None
    
def get_username():
    username = "guest"
    if g.user is not None:
        username = g.user['username']
    return username


def parse_band_range(request, from_form=False):
    minhash_band_range= 2
    arg_to_value = {
        # deactivate minhash bands
        0: 0,
        # 1: "Fast"
        1: 4,
        # 1: "Standard"
        2: 2,
        # 1: "Complete"
        3: 1
    }
    try:
        if from_form:
            minhash_band_range = int(request.form['minhashBandRange'])
        else:
            minhash_band_range = int(request.args.get('minhashBandRange', "2"))
        minhash_band_range = min(3, minhash_band_range)
        minhash_band_range = max(0, minhash_band_range)
    except:
        minhash_band_range = 2
    minhash_band_range = arg_to_value[minhash_band_range]
    return minhash_band_range


def parse_integer_query_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as int """
    param = None
    try:
        if request.args.get(query_param).startswith("0x"):
            param =  int(request.args.get(query_param), 16)
        else:
            param = int(request.args.get(query_param))
    except Exception:
        pass
    return param

def parse_integer_list_query_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as list of int (no brackets) """
    param = None
    try:
        if re.match("^\d+(?:[\s]*,[\s]*\d+)*$", request.args.get(query_param)):
            param = [int(element.strip()) for element in request.args.get(query_param).split(',')]
            param
    except Exception:
        pass
    return param


def parse_str_query_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as str """
    param = None
    try:
        param = request.args.get(query_param)
    except Exception:
        pass
    return param


def parse_checkbox_query_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as checkbox """
    param = False
    try:
        value = request.args.get(query_param)
        param = True if isinstance(value, str) and value.lower() in ["on", "true"] else False
    except Exception:
        pass
    return param


def parse_integer_post_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as int """
    param = None
    try:
        param = int(request.form.get(query_param))
    except Exception:
        pass
    return param


def parse_checkbox_post_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as checkbox """
    param = False
    try:
        value = request.form.get(query_param)
        param = True if isinstance(value, str) and value.lower() in ["on", "true"] else False
    except Exception:
        pass
    return param


def parseBaseAddrFromFilename(filename):
    # try to infer base addr from filename:
    baddr_match = re.search(re.compile("_0x(?P<base_addr>[0-9a-fA-F]{8,16})"), filename)
    if baddr_match:
        parsed_base_addr = int(baddr_match.group("base_addr"), 16)
        logging.info("Parsed base address from file name: 0x%08x %d", parsed_base_addr, parsed_base_addr)
        return parsed_base_addr
    logging.warning("No base address recognized, using None.")
    return None


def parseBitnessFromFilename(filename):
    # try to infer bitness from filename:
    baddr_match = re.search(re.compile("_0x(?P<base_addr>[0-9a-fA-F]{8,16})"), filename)
    if baddr_match:
        if len(baddr_match.group("base_addr")) > 8:
            logging.info("Parsed bitness from base addr len from file name: %s", filename)
            return 64
        else:
            return 32
    logging.warning("No base address recognized, using None.")
    return None


def ensure_local_data_paths(app, clear_data=False):
    # nuke both cache and temp folders
    nuke_paths = [
        app.instance_path + os.sep + "cache",
        app.instance_path + os.sep + "temp"
    ]
    # ensure the instance and cache folders exists
    ensure_paths = [
        app.instance_path + os.sep + "cache" + os.sep + "diagrams",
        app.instance_path + os.sep + "cache" + os.sep + "results",
        app.instance_path + os.sep + "temp" + os.sep + "reports",
        app.instance_path + os.sep + "temp" + os.sep + "diagrams",
        app.instance_path + os.sep + "temp" + os.sep + "uploads",
    ]
    if clear_data:
        for path in nuke_paths:
            shutil.rmtree(path)
    for path in ensure_paths:
        try:
            os.makedirs(path)
        except FileExistsError:
            pass


def get_mcritweb_version_from_setup():
    this_file_path = str(os.path.abspath(__file__))
    project_root = str(os.path.abspath(os.sep.join([this_file_path, "..", "..", ".."])))
    setup_path = os.path.abspath(os.sep.join([project_root, "setup.py"]))
    mcritweb_version = None
    with open(setup_path, "r") as fin:
        for line in fin.readlines():
            line = line.strip()
            match = re.search("version=\"(?P<version_str>\d+\.\d+\.\d+)\",", line)
            if match:
                mcritweb_version = match.group("version_str")
    return mcritweb_version


def get_full_picblock_matches(function_entry_a, function_entry_b):
    node_colors = {"a": {}, "b": {}}
    phb_a = set([pbh["hash"] for pbh in function_entry_a.picblockhashes])
    phb_b = set([pbh["hash"] for pbh in function_entry_b.picblockhashes])
    phb_match_addr_a = [pbh["offset"] for pbh in function_entry_a.picblockhashes if pbh["hash"] in phb_a.intersection(phb_b)]
    phb_match_addr_b = [pbh["offset"] for pbh in function_entry_b.picblockhashes if pbh["hash"] in phb_a.intersection(phb_b)]
    for addr in phb_match_addr_a:
        node_colors["a"][f"Node0x{addr:x}"] = "#00DDFF"
    for addr in phb_match_addr_b:
        node_colors["b"][f"Node0x{addr:x}"] = "#00DDFF"
    return node_colors

def get_all_picblock_matches(function_a, function_b):
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    smda_function_a = function_a.toSmdaFunction()
    smda_function_b = function_b.toSmdaFunction()
    sample_a = client.getSampleById(function_a.sample_id)
    sample_b = client.getSampleById(function_b.sample_id)
    node_colors = {"a": {}, "b": {}}
    all_phbs_a = []
    for block in smda_function_a.getBlocks():
        escaped_binary_seq = []
        for instruction in block.getInstructions():
            escaped_binary_seq.append(instruction.getEscapedBinary(IntelInstructionEscaper, escape_intraprocedural_jumps=True, lower_addr=sample_a.base_addr, upper_addr=sample_a.base_addr + sample_a.binary_size))
        as_bytes = bytes([ord(c) for c in "".join(escaped_binary_seq)])
        hashed = struct.unpack("Q", hashlib.sha256(as_bytes).digest()[:8])[0]
        all_phbs_a.append({"offset": block.offset, "hash": hashed})
    all_phbs_b = []
    for block in smda_function_b.getBlocks():
        escaped_binary_seq = []
        for instruction in block.getInstructions():
            escaped_binary_seq.append(instruction.getEscapedBinary(IntelInstructionEscaper, escape_intraprocedural_jumps=True, lower_addr=sample_b.base_addr, upper_addr=sample_b.base_addr + sample_b.binary_size))
        as_bytes = bytes([ord(c) for c in "".join(escaped_binary_seq)])
        hashed = struct.unpack("Q", hashlib.sha256(as_bytes).digest()[:8])[0]
        all_phbs_b.append({"offset": block.offset, "hash": hashed})
    phb_a = set([pbh["hash"] for pbh in all_phbs_a])
    phb_b = set([pbh["hash"] for pbh in all_phbs_b])
    phb_match_addr_a = [pbh["offset"] for pbh in all_phbs_a if pbh["hash"] in phb_a.intersection(phb_b)]
    phb_match_addr_b = [pbh["offset"] for pbh in all_phbs_b if pbh["hash"] in phb_a.intersection(phb_b)]
    for addr in phb_match_addr_a:
        node_colors["a"][f"Node0x{addr:x}"] = "#C0F4FF"
    for addr in phb_match_addr_b:
        node_colors["b"][f"Node0x{addr:x}"] = "#C0F4FF"
    return node_colors

def get_escaped_matches(smda_function_a, smda_function_b):
    node_colors = {"a": {}, "b": {}}
    all_escapes_a = []
    for block in smda_function_a.getBlocks():
        escaped_ins_seq = []
        for instruction in block.getInstructions():
            escaped_ins = IntelInstructionEscaper.escapeMnemonic(instruction.mnemonic) + " " + IntelInstructionEscaper.escapeOperands(instruction)
            escaped_ins_seq.append(escaped_ins)
        merged = ";".join(escaped_ins_seq)
        # print("0x%x" % block.offset, merged)
        hashed = struct.unpack("Q", hashlib.sha256(merged.encode("ascii")).digest()[:8])[0]
        all_escapes_a.append({"offset": block.offset, "hash": hashed})
    all_escapes_b = []
    for block in smda_function_b.getBlocks():
        escaped_ins_seq = []
        for instruction in block.getInstructions():
            escaped_ins = IntelInstructionEscaper.escapeMnemonic(instruction.mnemonic) + " " + IntelInstructionEscaper.escapeOperands(instruction)
            escaped_ins_seq.append(escaped_ins)
        merged = ";".join(escaped_ins_seq)
        # print("0x%x" % block.offset, merged)
        hashed = struct.unpack("Q", hashlib.sha256(merged.encode("ascii")).digest()[:8])[0]
        all_escapes_b.append({"offset": block.offset, "hash": hashed})
    phb_a = set([pbh["hash"] for pbh in all_escapes_a])
    phb_b = set([pbh["hash"] for pbh in all_escapes_b])
    phb_match_addr_a = [pbh["offset"] for pbh in all_escapes_a if pbh["hash"] in phb_a.intersection(phb_b)]
    phb_match_addr_b = [pbh["offset"] for pbh in all_escapes_b if pbh["hash"] in phb_a.intersection(phb_b)]
    for addr in phb_match_addr_a:
        node_colors["a"][f"Node0x{addr:x}"] = "#00ff00"
    for addr in phb_match_addr_b:
        node_colors["b"][f"Node0x{addr:x}"] = "#00ff00"
    return node_colors

def get_levenshtein_matches(smda_function_a, smda_function_b, unmatched_nodes):
    node_colors = {"a": {}, "b": {}}
    # across all blocks in unmatched nodes, collect tokens and map to symbols
    # token -> symbol, like "M REG, REG" -> 0
    # we use symbols from chr(0x20) to chr(0x7e), i.e. up to 94 printables, which "should always be enough (TM)""
    alphabet = {}
    num_symbols = 0
    # offset -> symbolified block
    candidate_blocks_a = {}
    for block in smda_function_a.getBlocks():
        if block.offset not in unmatched_nodes["a"]:
            continue
        symbolified_block = ""
        for instruction in block.getInstructions():
            escaped_ins = instruction.mnemonic + " " + IntelInstructionEscaper.escapeOperands(instruction)
            if escaped_ins not in alphabet:
                alphabet[escaped_ins] = chr(0x30 + num_symbols)
                num_symbols += 1
                if num_symbols > 94:
                    raise Exception("Basic Block contains too many tokens to compare.")
            symbolified_block += alphabet[escaped_ins]
        candidate_blocks_a[block.offset] = symbolified_block
    candidate_blocks_b = {}
    for block in smda_function_b.getBlocks():
        if block.offset not in unmatched_nodes["b"]:
            continue
        symbolified_block = ""
        for instruction in block.getInstructions():
            escaped_ins = instruction.mnemonic + " " + IntelInstructionEscaper.escapeOperands(instruction)
            if escaped_ins not in alphabet:
                alphabet[escaped_ins] = chr(0x30 + num_symbols)
                num_symbols += 1
                if num_symbols > 94:
                    raise Exception("Basic Block contains too many tokens to compare.")
            symbolified_block += alphabet[escaped_ins]
        candidate_blocks_b[block.offset] = symbolified_block

    # print(alphabet)
    by_score = {0: [], 1: [], 2: [], 3: []}
    for block_a, symbols_a in candidate_blocks_a.items():
        for block_b, symbols_b in candidate_blocks_b.items():
            distance = Levenshtein.distance(symbols_a, symbols_b, score_cutoff=3)
            if distance < 4:
                by_score[distance].append((block_a, block_b))
                # print(f"0x{block_a:x} 0x{block_b:x}: {symbols_a} || {symbols_b} - {distance}")
    used_blocks = set()
    for score, pairs in by_score.items():
        for pair in pairs:
            block_a, block_b = pair
            if block_a not in used_blocks and block_b not in used_blocks:
                node_colors["a"][f"Node0x{block_a:x}"] = score
                node_colors["b"][f"Node0x{block_b:x}"] = score
                used_blocks.add(block_a)
                used_blocks.add(block_b)
    # fix distances to colors
    distance_to_color = {
        99: "#FFA0A0",
        0: "#40ff40",
        1: "#c0ff80",
        2: "#FFFF40",
        3: "#FFCC40",
    }
    node_colors["a"] = {k: distance_to_color[v] for k, v in node_colors["a"].items()}
    node_colors["b"] = {k: distance_to_color[v] for k, v in node_colors["b"].items()}
    return node_colors


def get_matches_node_colors(function_id_a, function_id_b):
    # thresholded edit distance match over escaped instruction sequence: green to orange
    node_colors = {"a": {}, "b": {}}

    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    function_entry = client.getFunctionById(function_id_a, with_xcfg=True)
    other_function_entry = client.getFunctionById(function_id_b, with_xcfg=True)
    smda_function_a = function_entry.toSmdaFunction()
    smda_function_b = other_function_entry.toSmdaFunction()
    # no match / base color: bleak red
    for block in smda_function_a.getBlocks():
        node_colors["a"][f"Node0x{block.offset:x}"] = "#FFA0A0"
    for block in smda_function_b.getBlocks():
        node_colors["b"][f"Node0x{block.offset:x}"] = "#FFA0A0"
    # escaped blocks matches
    escaped_block_matches = get_escaped_matches(smda_function_a, smda_function_b)
    node_colors["a"].update(escaped_block_matches["a"])
    node_colors["b"].update(escaped_block_matches["b"])
    # ad-hoc picblock match (small BB): bleak teal
    smaller_picblock_matches = get_all_picblock_matches(function_entry, other_function_entry)
    node_colors["a"].update(smaller_picblock_matches["a"])
    node_colors["b"].update(smaller_picblock_matches["b"])
    # override "full" picblocks with 4+ addresses
    full_matches = get_full_picblock_matches(function_entry, other_function_entry)
    node_colors["a"].update(full_matches["a"])
    node_colors["b"].update(full_matches["b"])
    # compare everything not colored by now using our adapted Levenshtein
    unmatched_nodes = {
        "a": [int(k[6:], 16) for k, v in node_colors["a"].items() if v == "#FFA0A0"], 
        "b": [int(k[6:], 16) for k, v in node_colors["b"].items() if v == "#FFA0A0"], 
    }
    levenshtein_matches = get_levenshtein_matches(smda_function_a, smda_function_b, unmatched_nodes)
    node_colors["a"].update(levenshtein_matches["a"])
    node_colors["b"].update(levenshtein_matches["b"])
    return node_colors
