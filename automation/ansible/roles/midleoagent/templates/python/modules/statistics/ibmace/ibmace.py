from modules.statistics import common


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    common.post_csv_stats(
        "ibmace",
        lambda subtype: "ibmace" + subtype,
        website,
        webssl,
        inttoken,
        stat_data,
        lambda logdir, subtype: logdir + "ResourceStats_" + thisnode + "_*_" + subtype + ".txt",
    )


def getStat(thisqm, inpdata):
    return
