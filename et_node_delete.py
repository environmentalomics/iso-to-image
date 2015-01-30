#!/usr/bin/env python3
# Annoyingly, ElementTree does not allow you to find the parent of
# any given node.  But I think I can fix that.

import sys
import itertools
import xml.etree.ElementTree as ET

tree = ET.XML(
"""<foo xmlns:vbox="http://www.virtualbox.org/ovf/machine"><bar>
    <baz>1</baz>
    <vbox:baz>2</vbox:baz>
    <bam>3<zap/></bam>
    Some random text
    <!-- And a comment -->
</bar></foo>
""")

# Can I abuse e.tail to store a pointer to the parent node?
# Yes but it totally breaks the tree.
# Basically there is nowhere to stuff extra info in an Element node,
# so I have to use an external dict.

def get_parents(atree):
    tree_parents={atree:atree}
    stack = [atree]
    while stack:
        parent = stack.pop()
        for e in parent:
            stack.append(e)
            tree_parents[e] = parent
    #DEBUG
    for e in atree.iter():
        print("%s -> %s" % (tree_parents[e].tag, e.tag))

    return tree_parents

def del_by_name_1(atree, names):

    tps = get_parents(atree)

    #     for zapme in itertools.chain.from_iterable(atree.findall('.//' + i) for i in names):
    # Note - I explicitly want the node list to be calculated before the loop runs
    for zapme in (x for i in names for x in atree.findall('.//' + i)):
        tps[zapme].remove(zapme)

# Or maybe what I want is to just delete as I iterate?
# But you can't modify the tree as you iterate!  This has to be a 2-stage job.
def del_by_name_2(atree, names):

    stack = [atree]
    removals = []
    while stack:
        parent = stack.pop()
        for e in parent:
            print("Considering " + str(e))
            #Allow any:tag to match {*}tag
            ewctag = "{*}" + ( e.tag if not e.tag.startswith('{') else
                               e.tag[e.tag.find("}")+1:] )
            if e.tag in names or ewctag in names:
                print(" Removing " + str(e))
                removals.append((parent, e))
            else:
                stack.append(e)
                print(" Pushing " + str(e))

    for parent, e in removals: parent.remove(e)


del_by_name_1(tree, ('zap', 'baz', '{http://www.virtualbox.org/ovf/machine}baz'))

print("And the XML after zapping <zap> and <{*}baz>...")
ET.dump(tree)
