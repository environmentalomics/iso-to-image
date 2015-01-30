#!/usr/bin/env python3

# A while back I had an XSLT transformer script in Perl.  Nice and simple.
# I want to port that to Python to test it, then use XSLT to munge my .OVF
# docs and such stuff.

# Original at /home/tbooth/Documents/xmlpresentation/beer4libxsl.perl
# Run this on /home/tbooth/Documents/xmlpresentation/beerml.xml

# Note I have added a unicode output declaration to the XSLT and a matching decode
# step in do_trans, otherwise I just get a binary string.

import sys
import lxml.etree as ET

strongenough = 4.8

# For simplicity here, ss is a string and xmlin is a file handle
# and a string is returned.
def do_trans(ss, xmlin):
    xslt = ET.XSLT(ET.fromstring(ss.lstrip()))

    dom = ET.parse(xmlin)
    newdom = xslt(dom, strongenough = str(strongenough))

    return str(ET.tostring(newdom, pretty_print=True), encoding="UTF-8")



# The original XSLT stylesheet:
xslt_stylesheet = '''
<?xml version="1.0"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns="http://www.w3.org/1999/xhtml">

    <xsl:output encoding="UTF-8"/>
    <xsl:param name="strongenough"/>

    <xsl:template match="/">
        <html>
        <head><title>BEER</title></head> <body>
            <h3><u>Tasty Beers in List</u></h3><xsl:apply-templates/>
        </body> </html>
    </xsl:template>

    <xsl:template match="beer">
        <p>Beer from <xsl:value-of select="brewery"/> - <xsl:value-of select="@name"/>
        <xsl:if test="abv &lt; $strongenough">- <b>This be cooking beer!</b>
        </xsl:if> </p>
    </xsl:template>

</xsl:stylesheet>
'''

print(do_trans(xslt_stylesheet, sys.stdin))
