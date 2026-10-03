import unittest,tempfile
from mediation import parse_tree,winner_changes
from differential import flatten_graph,graph_deltas,model_deltas,xmlnode,ET
class Controls(unittest.TestCase):
    def test_traced_wall_clock_is_normalized(self):
        for sid,tag,a,b in [('mybatis__spring','timestamp','2026-09-29 16:53:40+0000','2026-09-29 16:59:54+0000'),('oshi__oshi','Build-Time','2026-09-29 17:24:33','2026-09-29 17:27:46')]:
            self.assertEqual(xmlnode(ET.fromstring(f'<{tag}>{a}</{tag}>'),sid),xmlnode(ET.fromstring(f'<{tag}>{b}</{tag}>'),sid))
    def test_untraced_timestamp_not_erased(self):
        self.assertNotEqual(xmlnode(ET.fromstring('<timestamp>2026-09-29 16:53:40+0000</timestamp>'),'fixture'),xmlnode(ET.fromstring('<timestamp>2026-09-29 16:59:54+0000</timestamp>'),'fixture'))
    def test_implicit_compile_scope_is_equivalent(self):
        a=xmlnode(ET.fromstring('<dependency><groupId>x</groupId><artifactId>a</artifactId><scope>compile</scope></dependency>'),'fixture')
        b=xmlnode(ET.fromstring('<dependency><artifactId>a</artifactId><groupId>x</groupId></dependency>'),'fixture')
        self.assertEqual(a,b)
    def test_omitted_node_not_selected(self):
        rows=parse_tree('x:root:pom:1\n+- x:a:jar:2:compile\n|  \\- (x:b:jar:1:compile - omitted for conflict with 3)\n\\- x:b:jar:3:compile\n')
        self.assertEqual(rows[2]['state'],'OMITTED_CONFLICT')
        self.assertEqual(rows[2]['conflict_winner'],'3')
        self.assertEqual(rows[2]['depth'],2)
        self.assertEqual(len(rows[2]['parent_path']),2)
    def test_mediation_needs_selected_version_evidence(self):
        a=parse_tree('x:root:pom:1\n\\- (x:b:jar:1:compile - omitted for conflict with 2)')
        b=parse_tree('x:root:pom:1\n\\- (x:b:jar:1:compile - omitted for conflict with 3)')
        self.assertEqual(winner_changes(a,b,[]),[])
        self.assertEqual(len(winner_changes(a,b,[{'type':'VERSION_CHANGED','identity':['x','b','jar','']}])) ,1)
    def tree(self,version='1',scope='compile',child=None):
        r={'groupId':'x','artifactId':'root','version':'1','type':'pom','children':[{'groupId':'x','artifactId':'lib','version':version,'type':'jar','scope':scope,'optional':'false'}]}
        if child:r['children'][0]['children']=[child]
        return flatten_graph(r)
    def test_identical(self):self.assertEqual(graph_deltas(self.tree(),self.tree()),[])
    def test_version_and_scope(self):
        self.assertEqual({d['type'] for d in graph_deltas(self.tree(),self.tree('2','test'))},{'VERSION_CHANGED','SCOPE_CHANGED'})
    def test_boolean_optional(self):self.assertFalse(self.tree()[1]['optional'])
    def test_parent_path(self):
        c={'groupId':'x','artifactId':'c','version':'3','type':'jar'}
        a=self.tree(child=c);b=self.tree('2',child=c)
        self.assertIn('PATH_CHANGED',{d['type'] for d in graph_deltas(a,b)})
    def test_property_order_and_whitespace(self):
        a=xmlnode(ET.fromstring('<properties>\n <x>1</x><a>2</a></properties>'),'fixture')
        b=xmlnode(ET.fromstring('<properties><a>2</a><x>1</x></properties>'),'fixture')
        self.assertEqual(a,b)
    def test_dependency_order_preserved(self):
        a=xmlnode(ET.fromstring('<dependencies><d>a</d><d>b</d></dependencies>'),'fixture')
        b=xmlnode(ET.fromstring('<dependencies><d>b</d><d>a</d></dependencies>'),'fixture')
        self.assertNotEqual(a,b)
    def test_timestamp_semantics_preserved(self):
        a=xmlnode(ET.fromstring('<properties/>'),'fixture')
        b=xmlnode(ET.fromstring('<properties><project.build.outputTimestamp>1980-01-01T00:00:00Z</project.build.outputTimestamp></properties>'),'fixture')
        self.assertTrue(model_deltas(a,b))
if __name__=='__main__':unittest.main()
