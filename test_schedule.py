import re
content = open('docs/swe-men-hockey.ics').read()
events = re.findall(r'SUMMARY:([^\r\n]+).*?DTSTART:([^\r\n]+)', content, re.DOTALL)
print("Generated events with dates and times:")
for summary, dtstart in events:
    date_obj = dtstart[:8]
    time_str = dtstart[9:13]
    month = date_obj[4:6]
    day = date_obj[6:8]
    hour = int(time_str[:2])
    minute = time_str[2:]
    print(f"  {summary:40} - {month}/{day} @ {hour:02d}:{minute}")
