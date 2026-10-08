import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import preview
import pace_config

class PreviewTest(unittest.TestCase):
    def test_embedded_settings_cannot_close_script(self):
        rendered = preview.render({**pace_config.defaults(), 'note': '</script><script>alert(1)</script>'})
        self.assertNotIn('</script><script>', rendered)
        self.assertIn('\\u003c/script>', rendered)

    @unittest.skipUnless(shutil.which('node'), 'Node required for browser formatter checks')
    def test_browser_formatter_matches_approaches_and_safe_text(self):
        source = preview.render(pace_config.defaults()).split('<script>')[1].split('</script>')[0]
        # Minimal DOM implements the actual renderer's text and style operations.
        harness = '''
const assert=require('node:assert/strict');
class Element {
 constructor(){this.style={};this.children=[];this.classList={add:()=>{}};this.type='';this.value='';}
 append(...items){this.children.push(...items)}
 replaceChildren(){this.children=[]}
 addEventListener(){}
}
const elements={};
const document={createElement:()=>new Element(),createTextNode:text=>({textContent:text}),getElementById:id=>elements[id]||(elements[id]=new Element())};
for(const id of ['bionic','answerFirst','chunks','actionMarkers'])document.getElementById(id).type='checkbox';
for(const id of ['length','anchorTrigger','driftGuard'])document.getElementById(id).type='number';
'''
        checks = '''
function marks(text,approach){return word(text,{...initial,bionicApproach:approach,bionicGradient:'off'}).children.map(s=>Number(s.style.fontWeight)===800)}
assert.deepEqual(marks('reading','third'),[true,true,true,false,false,false,false]);
assert.deepEqual(marks('rhythm','vowels'),[false,false,true,false,false,false]);
assert.deepEqual(marks('experience','third+anchor'),[true,true,true,true,false,false,false,false,true,false]);
assert.deepEqual(marks('école','vowels'),[true,false,true,false,true]);
const weights=word('reading',{...initial,bionicGradient:'weight'}).children.map(s=>s.style.fontWeight);
assert.equal(weights[0],800);assert.equal(weights.at(-1),400);
const p=prose('<script>alert(1)</script>',{...initial,bionic:false});
assert.equal(p.children.map(c=>c.textContent).join(''),'<script>alert(1)</script>');

// Formatting changes must not replace the passage.
const before=current;update();assert.equal(current,before);
el('text-type').value='technical';
const distinct=new Set();
for(let i=0;i<3;i++){newPassage();distinct.add(current.answer)}
assert.equal(distinct.size,3);
newPassage();assert.match(el('passage-status').textContent,/another round/);
el('text-type').value='narrative';newPassage();assert.equal(current.type,'narrative');
'''
        result = subprocess.run(['node', '-e', harness + source + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

from analytics_test_support import isolated_analytics
setUpModule, tearDownModule = isolated_analytics()
