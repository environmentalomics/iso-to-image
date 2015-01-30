#!/usr/bin/env python3

# I always get confused with how these logging modules work, so
# here is a practical example to help me.

import logging
L = logging.getLogger(__name__)

L.warn("The program is starting")

# In Python2 I need to make a default handler.  Python3 gives me one for free but
# I should still be explicit.
# Note the normal option is to just log at the root, and whichever bit of code runs
# this first gets to control the logging.
# Also note that there seems to be no option but to use old-style %-formatting here.
logging.basicConfig(format="%(levelname)1.1s: %(message)s", level=logging.WARN)

L.warn("Logging was configured")

L.debug("DEBUG1 - not printed")

L.warn("Now I want to debug")

# Set global debugging?  Or just for this logger?  Not sure.
L.setLevel(logging.DEBUG)

L.debug("DEBUG2 - will be printed")
L.info("This is for info")

L.warn("Now I want to stop debugging")


L.setLevel(logging.WARN)

L.warn("And I'm done")
L.debug("DEBUG3 - will not be printed")
