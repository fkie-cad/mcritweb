"""Parsing of request parameters and of metadata encoded in uploaded filenames.

Split out of utility.py so these can be imported - and tested - without pulling in
smda, mcrit or the database layer. Nothing here touches Flask globals: each helper
takes the request object as an argument. See issue #88.
"""

import logging
import re


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
    except Exception:
        minhash_band_range = 2
    minhash_band_range = arg_to_value[minhash_band_range]
    return minhash_band_range


def parse_integer_query_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as int """
    param = None
    try:
        value = request.args.get(query_param)
        if value is not None:
            if value.startswith("0x"):
                param = int(value, 16)
            else:
                param = int(value)
    except Exception:
        pass
    return param

def parse_integer_list_query_param(request, query_param:str):
    """ Try to find query_param in the request and parse it as list of int (no brackets) """
    param = None
    try:
        value = request.args.get(query_param)
        if value is not None and re.match(r"^\d+(?:[\s]*,[\s]*\d+)*$", value):
            param = [int(element.strip()) for element in value.split(',')]
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


def parse_choice_query_param(request, query_param:str, choices, default=None):
    """ Try to find query_param in the request and accept it only if it is one of choices """
    param = default
    try:
        value = request.args.get(query_param)
        if value in choices:
            param = value
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
        value = request.form.get(query_param)
        if value is not None:
            param = int(value)
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
