import unittest,json,sqlite3,time,re
from common import ROOT,normalize,qid,strip_number,QSTART
from search_questions import search,map_answer,query_parts

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn=sqlite3.connect(ROOT/'database/questions.sqlite')
        cls.all=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM questions')];conn.close()
        cls.good=next(q for q in cls.all if q['verification_status']=='VERIFIED' and not q['time_sensitive'] and len(q['options'])==4 and 30<len(q['question_text'])<200 and not re.search('[A-H][.、]',q['question_text']))
    def test_exact_answer_and_source(self):
        q=self.good;r=search(q['question_text'],q['options'],semantic=False)
        self.assertEqual(r['decision'],'DIRECT_ORIGINAL');self.assertTrue(r['match']['answer_source']);self.assertEqual(set(r['answer']),set(q['correct_answer']))
    def test_reordered_options(self):
        q=self.good;opts=dict(zip('ABCD',reversed(list(q['options'].values()))));r=search(q['question_text'],opts,semantic=False)
        self.assertEqual(r['decision'],'DIRECT_ORIGINAL')
        self.assertEqual(sorted(normalize(opts[k]) for k in r['answer']),sorted(normalize(v) for v in q['correct_answer_content']))
        self.assertEqual(qid(q['question_text'],opts),q['question_id'])
    def test_missing_option(self):
        q=self.good;opts=dict(q['options']);opts.pop('D');r=search(q['question_text'],opts,semantic=False)
        self.assertIsNone(r.get('answer'))
    def test_changed_number(self):
        q=self.good;r=search(q['question_text']+'（条件改为123456789元）',q['options'],semantic=False)
        self.assertIsNone(r.get('answer'))
    def test_changed_negation(self):
        q=self.good;r=search(q['question_text']+'（本题要求选不正确的一项）',q['options'],semantic=False)
        self.assertIsNone(r.get('answer'))
    def test_changed_option_content(self):
        q=self.good;opts=dict(q['options']);opts['A']+='（调整条件）';r=search(q['question_text'],opts,semantic=False)
        self.assertIsNone(r.get('answer'))
    def test_conflicts_withheld(self):
        q=next((q for q in self.all if q['verification_status']=='CONFLICT'),None)
        if q is None:self.skipTest('No conflicts present')
        self.assertIsNone(map_answer(q,q['options'])[0])
    def test_unverified_withheld(self):
        q=next(q for q in self.all if q['verification_status']=='UNVERIFIED')
        self.assertIsNone(map_answer(q,q['options'])[0])
    def test_dynamic_question_withheld(self):
        q=dict(self.good,time_sensitive=True)
        self.assertIsNone(map_answer(q,q['options'])[0])
    def test_duplicate_option_withheld(self):
        q=self.good;opts=dict(q['options']);opts['B']=opts['A'];self.assertIsNone(map_answer(q,opts)[0])
    def test_text_input_parsing(self):
        q=self.good;txt=q['question_text']+'\n'+'\n'.join(k+'. '+v for k,v in q['options'].items());stem,opts=query_parts(txt)
        self.assertEqual(normalize(stem),normalize(q['question_text']));self.assertEqual(opts,q['options'])
    def test_answer_provenance_all_verified(self):
        for q in self.all:
            if q['verification_status']=='VERIFIED':
                self.assertTrue(q['answer_source'],q['question_id']);self.assertTrue(q['correct_answer_content'],q['question_id'])
                self.assertTrue(any(s['verification_status']=='VERIFIED' for s in q['sources']))
    def test_parenthesized_sentence_number_preserved(self):
        self.assertEqual(strip_number('(1)进行良好的时间管理'),'(1)进行良好的时间管理')
    def test_appendix_question_heading(self):
        self.assertEqual(len(list(QSTART.finditer('试题1:第一题\n试题2:第二题'))),2)
    def test_answer_sequence_is_not_multiselect(self):
        from parse_questions import make_question
        rec={'source_id':'TEST','source_file':'fixture.pdf','source_archive':'fixture.zip'}
        block='这道单选题正确的是?\nA.甲\nB.乙\nC.丙\nD.丁\n【答案】:C,D,D,B,A'
        q=make_question(rec,{},[(0,len(block),{'location':'page:1','method':'native'})],block,0,len(block),'这道单选题正确的是?',{'options':dict(zip('ABCD','甲乙丙丁')),'cutoff':block.index('【答案】')},'1')
        self.assertEqual(q['verification_status'],'UNVERIFIED')
    def test_multiple_option_groups_not_verified(self):
        from parse_questions import make_question
        rec={'source_id':'TEST','source_file':'fixture.pdf','source_archive':'fixture.zip'}
        block='第一道题正确的是?\nA.甲\nB.乙\nC.丙\nD.丁\n答案:B\n第二道题?\nA.戊\nB.己\nC.庚\nD.辛\n答案:B'
        q=make_question(rec,{},[(0,len(block),{'location':'page:1','method':'native'})],block,0,len(block),'第一道题正确的是?',{'options':dict(zip('ABCD','甲乙丙丁')),'cutoff':block.index('答案:')},'1')
        self.assertEqual(q['verification_status'],'UNVERIFIED')
    def test_bracket_options(self):
        from parse_questions import clean,option_block
        block=clean('1.正确的一项是?\n[A]甲\n[B]乙\n[C]丙\n[D]丁\n答案:B')
        self.assertEqual(option_block(block)['options'],dict(zip('ABCD','甲乙丙丁')))

if __name__=='__main__':
    import io
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report=stream.getvalue();(ROOT/'reports/boundary_tests.txt').write_text(report,encoding='utf-8');print(report)
    raise SystemExit(0 if result.wasSuccessful() else 1)
