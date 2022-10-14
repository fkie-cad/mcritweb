import json

def get_sample_to_job_id(job_info):
    return json.loads(job_info.payload["params"])['0']


def score_to_color(score):
    if score >= 90:
        return "0080ff"  # dark blue
    elif score >= 80:
        return "00ffff"  # cyan
    elif score >= 70:
        return "00ff00"  # green 
    elif score >= 60:
        return "c0ff00"  # lime
    elif score >= 50:
        return "ffff00"  # yellow
    elif score >= 40:
        return "ffc000"  # orange
    elif score >= 30:
        return "ff8000"  # dark orange
    elif score >= 20:
        return "ff4000"  # red-orange
    elif score >= 10:
        return "ff0000"  # red
    elif score > 0:
        return "444444"  # light grey
    else:
        return "222222"  # dark grey / background