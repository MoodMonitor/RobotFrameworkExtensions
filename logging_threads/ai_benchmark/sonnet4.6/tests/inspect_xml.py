"""Inspect output.xml structure for quality verification."""
import sys
import xml.etree.ElementTree as ET


def inspect_test(xml_path, test_name_fragment, max_msgs=5):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    found = False
    for test in root.iter('test'):
        tname = test.get('name', '')
        if test_name_fragment in tname:
            found = True
            print(f"\n{'='*60}")
            print(f"TEST: {tname}")
            print(f"{'='*60}")
            _dump_body(test, depth=1, max_msgs=max_msgs)
    if not found:
        print(f"[!] No test matching '{test_name_fragment}' found in {xml_path}")


def _dump_body(node, depth, max_msgs):
    indent = "  " * depth
    msg_count = 0
    for child in node:
        tag = child.tag
        if tag == 'kw':
            ktype = child.get('type', 'KEYWORD')
            name = child.get('name', '?')
            owner = child.get('owner', '')
            # find status
            status = '?'
            for s in child:
                if s.tag == 'status':
                    status = s.get('status', '?')
                    break
            print(f"{indent}[KW type={ktype}] {name} ({owner}) -> {status}")
            _dump_body(child, depth + 1, max_msgs)
        elif tag == 'msg':
            if msg_count < max_msgs:
                ts = child.get('time', '')
                lvl = child.get('level', '')
                txt = (child.text or '')[:70]
                print(f"{indent}[MSG {lvl} @{ts[:23]}] {txt}")
            elif msg_count == max_msgs:
                print(f"{indent}... (more messages)")
            msg_count += 1
        elif tag == 'for':
            flavor = child.get('flavor', '')
            print(f"{indent}[FOR flavor={flavor}]")
            _dump_body(child, depth + 1, max_msgs)
        elif tag == 'iter':
            print(f"{indent}[ITER]")
            _dump_body(child, depth + 1, max_msgs)
        elif tag in ('if', 'try', 'while'):
            print(f"{indent}[{tag.upper()}]")
            _dump_body(child, depth + 1, max_msgs)
        elif tag == 'branch':
            btype = child.get('type', '')
            cond = child.get('condition', '')
            print(f"{indent}[BRANCH type={btype} cond={cond}]")
            _dump_body(child, depth + 1, max_msgs)


if __name__ == '__main__':
    xml_path = sys.argv[1] if len(sys.argv) > 1 else 'results_s1/output.xml'
    tests_to_show = sys.argv[2:] if len(sys.argv) > 2 else ['TC1', 'TC2', 'TC5']
    for frag in tests_to_show:
        inspect_test(xml_path, frag)
