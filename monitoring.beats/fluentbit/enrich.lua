cache = {}
ttl = 60

local function extract_message_after_error(line, error)
    if not line or line == "" then
        return ""
    end

    line = string.gsub(line, "^#+%s*", "")
    line = string.gsub(line, "[\r\n]+", " ")

    if error and error ~= "" then
        local _, finish = string.find(line, "<" .. error .. ">", 1, true)
        if finish then
            local rest = string.sub(line, finish + 1)
            local msg = string.match(rest, "%s*<([^<>].-)>%s*$")
            if msg and msg ~= "" then
                return msg
            end
        end
    end

    local last = nil
    for part in string.gmatch(line, "<([^<>]*)>") do
        if part and part ~= "" then
            last = part
        end
    end

    return last or line
end

function enrich_record(tag, timestamp, record)

    local error = record["error"]
    local line  = record["rawlog"] or record["log"] or ""

    if error == nil then
        return -1, timestamp, record
    end

    local clean_message = extract_message_after_error(line, error)

    record["monid"] = "weblogic_" .. error
    record["alerttime"] = os.date("%Y-%m-%d %H:%M:%S")
    record["message"] = string.sub(clean_message, 1, 500)

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