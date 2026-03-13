cache = {}
ttl = 60

function enrich_record(tag, timestamp, record)

    local error = record["error"]
    local line  = record["rawlog"] or record["log"] or ""

    if error == nil then
        return -1, timestamp, record
    end

    record["monid"] = "weblogic_" .. error
    record["alerttime"] = os.date("%Y-%m-%d %H:%M:%S")
    record["message"] = string.sub(line,1,500)

    record["rawlog"] = nil
    record["log"] = nil
    record["date"] = nil

    local key = record["monid"] .. record["message"]
    local now = os.time()

    if cache[key] ~= nil and (now - cache[key]) < ttl then
        return -1, timestamp, record
    end

    cache[key] = now

    return 1, timestamp, record
end