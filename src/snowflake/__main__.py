import time

from snowflake import make_snowflake, melt, to_datetime

t0 = int(time.time() * 1000)
sid = make_snowflake(t0, 0, 0, 0)
print(to_datetime(t0, True), sid)
assert melt(sid)[0] == t0
