"""Research-led README diagrams: original vector scenes, one restrained accent.
See ../ANIMATION_RESEARCH.md and ../ANIMATION_STORYBOARD.md for direction.
"""
from manim import *
import numpy as np
config.background_color='#151515'
INK='#e6e3dd'; GRAY='#858585'; FAINT='#454545'; ACCENT='#b6a6cd'; BG='#151515'

def txt(s,size=23,color=INK,mono=False):
    return Text(s,font='Consolas' if mono else 'Segoe UI',font_size=size,color=color)
def line(a,b,color=GRAY,width=1.6):return Line(a,b,color=color,stroke_width=width)
def dot(p,color=INK,r=.075):return Dot(p,radius=r,color=color)
def packet(n=5,pos=ORIGIN,color=INK):
    return VGroup(*[line([-.38,.45-i*.22,0],[.38-(i%2)*.15,.45-i*.22,0],color,2.4) for i in range(n)]).move_to(pos)
def travel(a,b):return CubicBezier(np.array(a),np.array(a)+DOWN*1.6,np.array(b)+DOWN*1.6,np.array(b),color=GRAY,stroke_width=1.4)

class Diagram(Scene):
    def header(self,k,title,detail):
        self.add(txt(k.upper(),15,GRAY).move_to([-6.25,3.48,0],aligned_edge=LEFT))
        title=txt(title,32).move_to([-6.25,2.98,0],aligned_edge=LEFT)
        if title.width>12.5:title.scale_to_fit_width(12.5).align_to(LEFT*6.25,LEFT)
        self.add(title,txt(detail,19,GRAY).move_to([-6.25,2.4,0],aligned_edge=LEFT))
        self.add(line([-6.25,2.08,0],[6.25,2.08,0],FAINT,1))
        self.caption=None
        self.add(txt('CONCEPTUAL DIAGRAM · NOT A BENCHMARK',12,GRAY).to_edge(DOWN,buff=.2))
    def note(self,s):
        n=txt(s,24).move_to([0,-2.98,0])
        if n.width>12.5:n.scale_to_fit_width(12.5)
        if self.caption is None:self.play(FadeIn(n),run_time=.25)
        else:self.play(FadeTransform(self.caption,n),run_time=.25)
        self.caption=n
    def rest(self):self.wait(1.8)

class Budget(Diagram):
    def construct(self):
        self.header('01 / allocation','Spend reasoning on the idea.','A hypothetical per-fold delegation versus this project’s coding task.')
        ys=[1,.05,-.9]
        left=VGroup(*[txt('agent task',21).move_to([-4.8,y,0]) for y in ys])
        folds=VGroup(*[txt(f'fold {i+1}',22).move_to([3.9,y,0]) for i,y in enumerate(ys)])
        paths=VGroup(*[line([-3.5,y,0],[2.9,y,0],GRAY) for y in ys])
        ticks=VGroup(*[line([3.48+j*.12,y-.45,0],[3.48+j*.12,y-.25,0],FAINT) for y in ys for j in range(8)])
        self.play(FadeIn(left),FadeIn(folds),LaggedStart(*[Create(p) for p in paths],lag_ratio=.3),run_time=1.4)
        self.note('Repeated execution does not require repeated delegation.')
        movers=VGroup(*[dot(p.get_start(),ACCENT) for p in paths]);self.add(movers)
        self.play(*[MoveAlongPath(d,p) for d,p in zip(movers,paths)],run_time=2.4,rate_func=linear)
        self.play(FadeOut(movers),run_time=.3)
        self.play(FadeOut(left[0]),FadeOut(left[2]),left[1].animate.move_to([-4.8,.05,0]),run_time=.8)
        code=packet(pos=[-1.9,.05,0]);code_label=txt('experiment code',18,ACCENT).next_to(code,UP,buff=.3)
        self.play(paths[0].animate.set_stroke(opacity=.1),paths[2].animate.set_stroke(opacity=.1),Create(code),FadeIn(code_label),run_time=.9)
        self.note('Choose Claude or Codex to write one experiment.')
        self.play(Transform(left[1],txt('selected agent',21).move_to(left[1])),run_time=.5)
        fan=VGroup(*[CubicBezier(np.array([-.9,.05,0]),np.array([.7,.05,0]),np.array([1.4,y,0]),np.array([2.9,y,0]),color=INK,stroke_width=1.6) for y in ys])
        python=txt('Python',23,ACCENT).move_to([.5,1.6,0]);self.play(FadeOut(paths),Create(fan),FadeIn(python),run_time=1)
        markers=VGroup(*[dot(p.get_start(),ACCENT) for p in fan]);self.add(markers)
        self.play(*[MoveAlongPath(d,p) for d,p in zip(markers,fan)],run_time=2,rate_func=linear)
        self.play(FadeOut(markers),Create(ticks),run_time=.5)
        self.note('Python repeats folds, scoring, and blends within your limits.')
        self.play(LaggedStart(*[t.animate.set_color(ACCENT) for t in ticks],lag_ratio=.035),run_time=1.5)
        limit=line([5.1,1.5,0],[5.1,-1.4,0],ACCENT,2);self.play(Create(limit),FadeIn(txt('bounded',17,GRAY).next_to(limit,RIGHT)),run_time=.7)
        self.rest()

class Supervisor(Diagram):
    def construct(self):
        self.header('02 / independence','The output has to fit the evidence.','The agent writes the experiment; the supervisor checks the result.')
        writer=txt('writer',22).move_to([-5.1,1.3,0]);test=txt('expected IDs',21).move_to([0,1.3,0]);judge=txt('scorer',22).move_to([5,1.3,0])
        self.add(writer,test,judge)
        expected=VGroup(*[Circle(radius=.08,color=GRAY,stroke_width=1.7).move_to([.6,.8-i*.35,0]) for i in range(5)])
        ids=VGroup(*[txt(str(i+1),16,GRAY,True).move_to([1,.8-i*.35,0]) for i in range(5)])
        rows=VGroup(*[line([-5.5,.8-i*.35,0],[-4.7,.8-i*.35,0],INK,2.5) for i in [0,1,3,4]])
        self.play(LaggedStart(*[Create(r) for r in rows],lag_ratio=.16),FadeIn(expected),FadeIn(ids),run_time=1)
        self.note('Four prediction rows arrive. Five IDs were expected.')
        self.play(rows.animate.shift(RIGHT*4.6),run_time=1.6)
        gap=Circle(radius=.2,color=ACCENT,stroke_width=2).move_to([.6,.1,0]);missing=txt('missing row',18,ACCENT).move_to([2,.1,0])
        self.play(Create(gap),FadeIn(missing),run_time=.6);self.wait(.8)
        path=travel([-1,.1,0],[-5.1,.1,0]);self.play(Create(path),run_time=.6)
        self.play(rows.animate.shift(LEFT*4.6),run_time=1.4)
        self.note('Return for repair before accepting a score.')
        fifth=line([-5.5,.1,0],[-4.7,.1,0],ACCENT,2.5);self.play(Create(fifth),FadeOut(gap),FadeOut(missing),run_time=.8)
        repaired=VGroup(*rows,fifth);self.play(repaired.animate.shift(RIGHT*4.6),run_time=1.5)
        matched=VGroup(*[dot(c.get_center(),ACCENT,.055) for c in expected]);self.play(FadeIn(matched),run_time=.6)
        self.note('Complete output proceeds to independent scoring.')
        self.play(repaired.animate.shift(RIGHT*5),run_time=1.4)
        self.play(FadeOut(path),run_time=.4)
        axis=line([3.4,-1.4,0],[6,-1.4,0]);self.play(Create(axis),run_time=.4)
        old=dot([4.2,-1.4,0],GRAY);new=dot([5.35,-1.4,0],ACCENT)
        self.play(FadeIn(old),FadeIn(txt('best so far',16,GRAY).next_to(old,DOWN)),run_time=.4)
        self.play(FadeIn(new),FadeIn(txt('candidate',16,ACCENT).next_to(new,DOWN)),run_time=.5)
        self.note('Only measured, comparable improvement can replace the champion.')
        self.rest()

class Search(Diagram):
    def construct(self):
        self.header('03 / search','Explore alternatives. Bound the frontier.','A small portfolio, rather than expanding every continuation.')
        root=dot([-5.5,.1,0],ACCENT,.1);centers=[[-2.2,1.5-i*.72,0] for i in range(5)]
        trunk=VGroup(*[line(root.get_center(),p,GRAY) for p in centers]);nodes=VGroup(*[dot(p) for p in centers])
        self.play(FadeIn(root),LaggedStart(*[Create(x) for x in trunk],lag_ratio=.13),FadeIn(nodes),run_time=1.3)
        twigs=VGroup();leaves=VGroup()
        for p in centers:
            for j in range(4):
                q=[1.2,p[1]+(j-1.5)*.14,0];twigs.add(line(p,q,FAINT,1));leaves.add(dot(q,GRAY,.035))
        self.play(LaggedStart(*[Create(x) for x in twigs],lag_ratio=.025),FadeIn(leaves),run_time=1.6)
        more=VGroup(*[line(d.get_center(),[5.8,d.get_y()+(.1 if j%2 else -.1),0],FAINT,.8) for j,d in enumerate(leaves)])
        self.play(LaggedStart(*[Create(x) for x in more],lag_ratio=.025),run_time=1.1)
        self.note('Each expanded branch adds more work to evaluate.')
        boundary=DashedLine([-.8,1.8,0],[-.8,-1.9,0],color=ACCENT,dash_length=.1)
        self.play(Create(boundary),twigs.animate.set_stroke(opacity=.12),more.animate.set_stroke(opacity=.08),leaves.animate.set_opacity(.18),run_time=1)
        title=txt('5 active directions',21,ACCENT).move_to([2.7,1.75,0]);self.play(FadeIn(title),run_time=.5)
        self.note('Keep at most five active directions; rank them from evidence.')
        bracket=VGroup(line([-2.55,1.7,0],[-2.55,1.3,0],ACCENT,2.5),line([-2.65,1.7,0],[-2.55,1.7,0],ACCENT),line([-2.65,1.3,0],[-2.55,1.3,0],ACCENT))
        self.play(Create(bracket),run_time=.4)
        for i in [1,3]:
            self.play(bracket.animate.shift(DOWN*(.72 if i==1 else 1.44)),trunk[i].animate.set_color(ACCENT),run_time=1.1)
            self.play(trunk[i].animate.set_color(GRAY),run_time=.4)
        self.note('Exploration turns revisit less-tried directions.')
        self.play(Transform(nodes[3],dot(centers[3],ACCENT,.12)),run_time=.6);self.rest()

class Memory(Diagram):
    def construct(self):
        self.header('04 / memory','Keep evidence. Rebuild context.','Sessions can end without erasing the experiment history.')
        record=VGroup(*[line([-5.6,1.5-i*.25,0],[-2.7+(i%3)*.22,1.5-i*.25,0],GRAY,1.5) for i in range(12)])
        tags=VGroup(*[dot([-5.85,1.5-i*.25,0],ACCENT,.035) for i in [1,5,9]])
        self.play(LaggedStart(*[Create(x) for x in record],lag_ratio=.04),FadeIn(tags),run_time=1.3)
        self.add(txt('persistent records',20,GRAY).move_to([-4.3,1.9,0]))
        brief=VGroup(*[line([-.5,.8-i*.35,0],[1.15-i*.2,.8-i*.35,0],INK,2.2) for i in range(3)])
        self.note('Select useful results instead of replaying every old log.')
        self.play(*[TransformFromCopy(record[i],b) for i,b in zip([1,5,9],brief)],run_time=1.6)
        self.play(FadeIn(txt('brief',20).next_to(brief,UP,buff=.35)),run_time=.4)
        session=Circle(radius=.64,color=INK,stroke_width=1.5).move_to([4.7,.45,0]);one=txt('1',30,mono=True).move_to(session)
        self.play(Create(session),FadeIn(one),run_time=.7)
        transfer=brief.copy();self.play(transfer.animate.scale(.25).move_to(session.get_center()+DOWN*.3),run_time=1.1);self.play(FadeOut(transfer),run_time=.3)
        self.note('The session ends. Its stored evidence stays put.')
        self.play(Uncreate(session),FadeOut(one),FadeOut(brief),run_time=1);self.wait(.6)
        session=Circle(radius=.64,color=INK,stroke_width=1.5).move_to([4.7,.45,0])
        two=txt('2',30,mono=True).move_to([4.7,.45,0]);self.play(Create(session),FadeIn(two),run_time=.8)
        self.play(*[TransformFromCopy(record[i],b) for i,b in zip([1,5,9],brief)],run_time=1.1)
        transfer=brief.copy();self.play(transfer.animate.scale(.25).move_to(session.get_center()+DOWN*.3),run_time=1.4);self.play(FadeOut(transfer),run_time=.3)
        self.note('A fresh session receives context from the same saved evidence.')
        self.add(txt('fresh session',19,GRAY).next_to(session,DOWN,buff=.4));self.rest()

class Validation(Diagram):
    def construct(self):
        self.header('05 / validation','Change the candidate. Keep the exam.','Fixed row identities and folds make experiments comparable.')
        cells=VGroup(*[Rectangle(width=.57,height=.65,color=GRAY,stroke_width=1,fill_opacity=0).move_to([-5.6+i*.72,.5,0]) for i in range(16)])
        labels=VGroup(*[txt(str(i+1),16,GRAY,True).next_to(c,DOWN,buff=.18) for i,c in enumerate(cells)])
        hatch=VGroup()
        for c in cells[10:13]:
            for k in [-.15,0,.15]:hatch.add(line(c.get_center()+[-.2,k-.12,0],c.get_center()+[.2,k+.12,0],ACCENT,1.4))
        self.play(LaggedStart(*[Create(c) for c in cells],lag_ratio=.035),FadeIn(labels),run_time=1.3)
        self.play(Create(hatch),run_time=.8)
        held=txt('held-out rows',20,ACCENT).move_to([2.3,1.6,0]);self.play(FadeIn(held),run_time=.4)
        self.note('These same rows stay outside training for this comparison.')
        a=txt('candidate A',23).move_to([-3.8,-1.2,0]);self.play(FadeIn(a),run_time=.4)
        pointers=VGroup(*[line([-3.8,-.85,0],c.get_bottom(),FAINT,1) for i,c in enumerate(cells) if i not in [10,11,12]])
        self.play(LaggedStart(*[Create(p) for p in pointers],lag_ratio=.025),run_time=1.1)
        self.play(Transform(a,txt('candidate B',23).move_to(a)),run_time=.8)
        self.note('Change the model; evaluate against the same held-out rows.')
        moved=hatch.copy();self.play(moved.animate.shift(RIGHT*.72),hatch.animate.set_stroke(opacity=.15),run_time=1)
        warn=txt('different exam',19,ACCENT).move_to([4.8,-1.1,0]);self.play(FadeIn(warn),run_time=.4)
        self.note('Moving the exam would confound the comparison.')
        self.play(moved.animate.shift(LEFT*.72),run_time=1.1);self.play(FadeOut(moved),hatch.animate.set_stroke(opacity=1),FadeOut(warn),run_time=.3)
        self.play(Transform(a,txt('candidate C',23).move_to(a)),run_time=.8)
        self.note('Same data. Same scoring rule. A meaningful comparison.')
        self.rest()

class Ensemble(Diagram):
    def construct(self):
        self.header('06 / ensembles','Different mistakes can cancel.','Illustrative residuals on the same held-out rows; lower error is not guaranteed.')
        xs=np.linspace(-5.4,5.4,13);ya=np.array([.45,1,1.35,.8,.2,-.4,-1,-.7,-.1,.6,1.1,.7,.25]);yb=-ya*.8+np.array([.1,-.1,.05,.12,.06,-.1,.05,.1,-.1,.05,.05,-.08,.02])
        baseline=line([-6,-.2,0],[6,-.2,0],GRAY,1.2);self.play(Create(baseline),run_time=.6)
        self.add(txt('0 error',16,GRAY).next_to(baseline,LEFT,buff=.05))
        a=VGroup(*[dot([x,y-.2,0],INK,.06) for x,y in zip(xs,ya)])
        b=VGroup(*[Circle(radius=.07,color=INK,stroke_width=1.4).move_to([x,y-.2,0]) for x,y in zip(xs,yb)])
        self.add(txt('A: filled',19).move_to([-4.5,1.65,0]),txt('B: open',19,GRAY).move_to([-2.1,1.65,0]))
        self.play(LaggedStart(*[FadeIn(p) for p in a],lag_ratio=.035),run_time=.8);self.play(LaggedStart(*[Create(p) for p in b],lag_ratio=.035),run_time=.8)
        pairs=VGroup(*[line(p.get_center(),q.get_center(),FAINT,1) for p,q in zip(a,b)])
        self.play(Create(pairs),run_time=.8);self.note('Compare each pair of errors for the same row.')
        mid=VGroup(*[dot([x,(u+v)/2-.2,0],ACCENT,.075) for x,u,v in zip(xs,ya,yb)])
        i=2;self.play(a[i].animate.set_color(ACCENT),b[i].animate.set_stroke(ACCENT),run_time=.4)
        ca=a[i].copy();cb=b[i].copy();self.add(ca,cb)
        self.play(ca.animate.move_to(mid[i]),cb.animate.move_to(mid[i]),run_time=1.7)
        self.play(FadeOut(ca),FadeOut(cb),FadeIn(mid[i]),run_time=.3)
        self.note('Their average lies at the midpoint, closer to zero here.')
        movers=VGroup(*[p.copy() for j,p in enumerate(a) if j!=i],*[p.copy() for j,p in enumerate(b) if j!=i]);self.add(movers)
        targets=[mid[j].get_center() for j in range(13) if j!=i]*2
        self.play(*[p.animate.move_to(q) for p,q in zip(movers,targets)],a.animate.set_opacity(.25),b.animate.set_stroke(opacity=.25),run_time=2)
        self.play(FadeOut(movers),FadeIn(mid),pairs.animate.set_stroke(opacity=.15),run_time=.4)
        self.note('Complementarity matters as well as standalone quality.')
        self.wait(1.5)
        self.play(FadeOut(mid),a.animate.set_opacity(1),b.animate.set_stroke(opacity=1),pairs.animate.set_stroke(opacity=1),run_time=1)
        self.note('Keep a blend only when held-out checks support it.')
        self.rest()
