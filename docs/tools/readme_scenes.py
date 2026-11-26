"""README-only explanatory animations. Manim Community; no generated imagery.
Render: python docs/tools/render_readme.py
The diagrams are conceptual, not benchmark measurements.
"""
from manim import *
import numpy as np
config.background_color='#0b1018'
B='#67c7ef'; Y='#f7d774'; G='#85d5aa'; R='#ec8c91'; M='#8995a6'; W='#edf0f6'

def label(s,size=23,color=W):return Text(s,font='Segoe UI',font_size=size,color=color)
def serif(s,size=34,color=W):return Text(s,font='Cambria',font_size=size,color=color)
def node(s,pos,color=B,w=2.5):
    box=RoundedRectangle(width=w,height=.85,corner_radius=.12,stroke_color=color,stroke_width=2,fill_color='#101e2a',fill_opacity=.65).move_to(pos)
    t=label(s,22,color).move_to(box)
    if t.width>w-.25:t.scale_to_fit_width(w-.25)
    return VGroup(box,t)
def arrow(a,b,color=B):return Arrow(a,b,buff=.12,color=color,stroke_width=2.5,max_tip_length_to_length_ratio=.12)
class Explainer(Scene):
    def heading(self,title,subtitle,source):
        self.add(serif(title,36).to_edge(UP,buff=.42),label(subtitle,21,M).to_edge(UP,buff=1.12))
        self.add(label(source+'  |  Conceptual illustration',14,M).to_edge(DOWN,buff=.25))
        self.caption=label('',24).move_to(DOWN*2.95)
    def say(self,text):
        n=label(text,24,Y).move_to(DOWN*2.95)
        if n.width>12.7:n.scale_to_fit_width(12.7)
        if self.caption in self.mobjects:self.play(ReplacementTransform(self.caption,n),run_time=.45)
        else:self.play(FadeIn(n,shift=UP*.1),run_time=.45)
        self.caption=n
    def pulse(self,path,color=Y,seconds=1):
        dot=Dot(radius=.065,color=color).move_to(path.get_start());self.add(dot)
        self.play(MoveAlongPath(dot,path),run_time=seconds,rate_func=smooth);self.remove(dot)
    def finish(self):self.wait(2.5)

class Budget(Explainer):
    def construct(self):
        self.heading('Why one coding agent?', 'Spend reasoning on the hypothesis. Let Python do the repetition.', 'Design constraints + autoresearch')
        claude=node('Claude Code',LEFT*4+UP*1.05);codex=node('Codex',LEFT*4+DOWN*.05)
        gate=node('Your selection',LEFT*.8,w=2.4);experiment=node('Experiment',RIGHT*3.8)
        a=arrow(claude.get_right(),gate.get_left());b=arrow(codex.get_right(),gate.get_left(),M);c=arrow(gate.get_right(),experiment.get_left())
        self.play(FadeIn(claude),FadeIn(codex),Create(a),Create(b),FadeIn(gate),Create(c),FadeIn(experiment),run_time=1.5)
        self.say('Claude OR Codex: your subscription, your model and effort settings.')
        self.play(codex.animate.set_opacity(.25),b.animate.set_opacity(.2));self.pulse(a);self.pulse(c)
        self.say('A single selected agent writes the code; it is not a permanent swarm.')
        swarm=VGroup(*[Circle(radius=.17,color=M).move_to([-.8+(j%5)*.55,1.7+(j//5)*.45,0]) for j in range(10)])
        self.play(LaggedStart(*[Create(x) for x in swarm],lag_ratio=.08),run_time=1)
        self.play(swarm.animate.set_opacity(.15),run_time=.7)
        tasks=VGroup(*[node(s,[-4+j*2.7,-1.35,0],G,w=2.25) for j,s in enumerate(['folds','seeds','scoring','blending'])])
        bracket=Brace(tasks,DOWN,color=G);txt=label('Deterministic Python',20,G).next_to(bracket,DOWN,buff=.12)
        self.play(LaggedStart(*[FadeIn(x,shift=UP*.2) for x in tasks],lag_ratio=.2),GrowFromCenter(bracket),FadeIn(txt),run_time=1.8)
        self.say('Routine computation does not need a fresh model conversation.')
        self.play(Indicate(tasks,color=G),run_time=1.2);self.wait(1)
        self.say('Quota or resource limit reached? Save state and stop; no paid fallback.')
        self.play(c.animate.set_color(Y),gate[0].animate.set_stroke(Y),run_time=.7);self.finish()

class Supervisor(Explainer):
    def construct(self):
        self.heading('Why separate the writer from the judge?', 'A claim becomes evidence only after an independent check.', 'ML Agent Harness + local controller')
        agent=node('Coding agent',[-4.5,.6,0]);check=node('Smoke test',[-.6,.6,0]);scorer=node('Frozen scorer',[4,.6,0],G)
        a=arrow(agent.get_right(),check.get_left());b=arrow(check.get_right(),scorer.get_left(),G)
        self.play(FadeIn(agent),FadeIn(check),FadeIn(scorer),Create(a),Create(b),run_time=1.3)
        self.say('The agent writes an experiment. The supervisor owns the checks.')
        script=VGroup(*[Line(LEFT*.25,RIGHT*.25,color=B).shift(DOWN*i*.12) for i in range(4)]).move_to(agent.get_top()+UP*.35)
        self.play(script.animate.move_to(check.get_top()+UP*.35),run_time=1.2)
        cross=Cross(check,stroke_color=R,stroke_width=3)
        self.play(Create(cross),run_time=.5)
        self.say('Broken code returns for repair before an expensive full run.')
        returnpath=ArcBetweenPoints(check.get_bottom()+DOWN*.2,agent.get_bottom()+DOWN*.2,angle=-PI/1.5,color=R)
        self.play(Create(returnpath),run_time=.7);self.play(MoveAlongPath(script,returnpath),run_time=1.4)
        self.play(FadeOut(cross),FadeOut(returnpath));self.play(script.animate.move_to(check.get_top()+UP*.35),run_time=1)
        self.play(check[0].animate.set_stroke(G));self.play(script.animate.move_to(scorer.get_top()+UP*.35),run_time=1)
        self.play(FadeOut(script),run_time=.3)
        self.say('Only valid outputs reach independent scoring and champion comparison.')
        best=node('Champion',RIGHT*3.9+DOWN*1.75,Y);down=arrow(scorer.get_bottom(),best.get_top(),Y)
        self.play(Create(down),FadeIn(best));self.pulse(down)
        back=ArcBetweenPoints(best.get_left(),agent.get_bottom(),angle=-PI/3,color=B)
        self.play(Create(back),run_time=1);self.pulse(back,seconds=1.5)
        self.say('Measured results return to the next brief. The agent never grades itself.')
        self.finish()

class Search(Explainer):
    def construct(self):
        self.heading('Why a small portfolio instead of an endless tree?', 'Explore alternatives without paying to expand every possibility.', 'MLEvolve + AIDE; simplified local portfolio')
        root=Dot(UP*1.4,radius=.12,color=Y);kids=[np.array([-4+2*j,0,0]) for j in range(5)]
        edges=VGroup(*[Line(root.get_center(),p,color=M,stroke_width=1.5) for p in kids]);dots=VGroup(*[Dot(p,radius=.085,color=B) for p in kids])
        self.play(GrowFromCenter(root),LaggedStart(*[Create(x) for x in edges],lag_ratio=.13),FadeIn(dots),run_time=1.6)
        names=VGroup(*[label(s,18).next_to(d,DOWN,buff=.2) for s,d in zip(['baseline','features','model','representation','solver'],dots)])
        self.play(FadeIn(names));self.say('Keep a few distinct hypotheses alive, not every possible continuation.')
        leaves=VGroup();twigs=VGroup()
        for j,p in enumerate(kids):
            for k in range(4):
                q=p+np.array([-.65+.43*k,-1.45,0]);leaves.add(Dot(q,radius=.035,color=M));twigs.add(Line(p,q,color=M,stroke_width=.8))
        self.play(LaggedStart(*[Create(x) for x in twigs],lag_ratio=.02),FadeIn(leaves),run_time=1.2)
        self.say('Expanding everything multiplies runs, context, and computation.')
        self.play(twigs.animate.set_opacity(.15),leaves.animate.set_opacity(.15),run_time=1)
        self.play(edges[1].animate.set_color(Y),dots[1].animate.scale(1.6).set_color(Y),run_time=.7)
        self.say('Prioritize observed wins, uncertainty, feasibility, and expected cost.')
        self.pulse(edges[1]);self.wait(.8)
        self.play(edges[1].animate.set_color(B),dots[1].animate.scale(1/1.6).set_color(B),edges[3].animate.set_color(Y),dots[3].animate.scale(1.6).set_color(Y),run_time=1)
        self.say('Reserve exploration turns so an overlooked direction can return.')
        self.pulse(edges[3]);self.play(Indicate(names[3],color=Y),run_time=1)
        cap=serif('At most 5 active directions',27,G).move_to(DOWN*2.15)
        self.play(Write(cap));self.finish()

class Memory(Explainer):
    def construct(self):
        self.heading('Why store evidence outside the conversation?', 'Context can end. The experiment history must survive.', 'ML-Master / EvoMaster memory references; local checkpoints')
        log=VGroup(*[Line([-5,1.6-j*.24,0],[-1.8+(j%3)*.25,1.6-j*.24,0],color=B,stroke_width=2) for j in range(10)])
        logtitle=label('Run artifacts + ledger',21,B).move_to([-3.5,2.1,0])
        brief=node('Compact brief',[3,.55,0],Y,w=3)
        self.play(LaggedStart(*[Create(x) for x in log],lag_ratio=.09),FadeIn(logtitle),FadeIn(brief),run_time=1.5)
        self.say('Record code, scores, failures, and attributed discoveries.')
        flow=arrow(LEFT*1.2+UP*.55,RIGHT*1.35+UP*.55,Y);self.play(Create(flow))
        notes=VGroup(*[label(s,19,G).move_to([3,1.95-j*.35,0]) for j,s in enumerate(['what worked','what failed','what to try next'])])
        self.play(LaggedStart(*[TransformFromCopy(log[j*3:j*3+3],n) for j,n in enumerate(notes)],lag_ratio=.3),run_time=2)
        self.say('Retrieve the useful evidence instead of replaying the entire history.')
        session=node('Agent session',[3,-1.5,0]);link=arrow(brief.get_bottom(),session.get_top())
        self.play(Create(link),FadeIn(session));self.pulse(link)
        self.say('A stopped session is disposable; its saved results are not.')
        self.play(FadeOut(session,shift=DOWN*.3),FadeOut(link),run_time=.8);self.wait(.5)
        fresh=node('Fresh session',[3,-1.5,0],G)
        self.play(FadeIn(fresh),Create(link));self.pulse(link,G,1.4)
        back=ArcBetweenPoints(fresh.get_left(),log.get_bottom(),angle=-PI/3,color=B)
        self.play(Create(back),run_time=.8);self.pulse(back,seconds=1.3)
        self.say('Rebuild the next brief from persistent state, then continue learning.')
        self.finish()

class Validation(Explainer):
    def construct(self):
        self.heading('Why freeze the exam?', 'A changing validation split can masquerade as model progress.', 'Frozen validation contract; MLE-bench evaluation reference')
        rows=VGroup(*[VGroup(*[Rectangle(width=1,height=.34,stroke_width=1,stroke_color=M,fill_color=B if j!=i else Y,fill_opacity=.75) for j in range(5)]).arrange(RIGHT,buff=.08) for i in range(3)]).arrange(DOWN,buff=.35).move_to(LEFT*2.2+UP*.3)
        labels=VGroup(*[label(f'fold {i+1}',18).next_to(row,LEFT,buff=.25) for i,row in enumerate(rows)])
        self.play(LaggedStart(*[FadeIn(x,shift=RIGHT*.2) for x in rows],lag_ratio=.2),FadeIn(labels),run_time=1.2)
        self.say('Training rows are blue. Held-out rows are gold. Keep the split fixed.')
        model=node('Candidate A',[3.8,1,0]);score=node('Measured score',[3.8,-.5,0],G)
        edge=arrow(model.get_bottom(),score.get_top(),G);self.play(FadeIn(model),Create(edge),FadeIn(score));self.pulse(edge)
        self.say('Change the model while keeping data, row identity, and scoring comparable.')
        nextmodel=node('Candidate B',model.get_center(),Y)
        self.play(ReplacementTransform(model,nextmodel),rows[1][1].animate.set_fill(B),rows[1][2].animate.set_fill(Y),run_time=1)
        warn=label('Different exam?',22,R).move_to([-.7,-1.7,0]);self.play(Write(warn))
        self.say('If the exam also changes, an apparent gain becomes ambiguous.')
        self.play(rows[1][1].animate.set_fill(Y),rows[1][2].animate.set_fill(B),FadeOut(warn),run_time=1)
        brace=Brace(rows,RIGHT,color=Y);freeze=label('frozen',20,Y).next_to(brace,RIGHT,buff=.1)
        self.play(GrowFromCenter(brace),FadeIn(freeze));self.pulse(edge,G,1.3)
        self.say('Promote from validation evidence, not public-leaderboard chasing.')
        self.play(Indicate(rows,color=Y),run_time=1);self.finish()

class Ensemble(Explainer):
    def construct(self):
        self.heading('Why keep a model that loses on its own?', 'Different mistakes can be more useful than another copy of the winner.', 'Chris Deotte S6E5 review; held-out ensemble checks')
        axes=Axes(x_range=[0,8,2],y_range=[-2,2,1],x_length=11,y_length=3.4,tips=False,axis_config={'color':M,'stroke_width':1.2}).move_to(UP*.05)
        a=axes.plot(lambda x:1.2*np.sin(x),x_range=[0,8],color=B)
        b=axes.plot(lambda x:-np.sin(x)+.12*np.cos(2*x),x_range=[0,8],color=R)
        lab=VGroup(label('A errors',21,B),label('B errors',21,R)).arrange(RIGHT,buff=.7).move_to(UP*2.15)
        self.play(Create(axes),Create(a),FadeIn(lab[0]),run_time=1.5)
        self.say('Think of each curve as prediction error across the same held-out rows.')
        self.play(Create(b),FadeIn(lab[1]),run_time=1.4)
        self.say('A different model can miss in a different direction.')
        markers=VGroup()
        for x in np.linspace(.7,7.3,8):
            markers.add(Line(axes.c2p(x,1.2*np.sin(x)),axes.c2p(x,-np.sin(x)+.12*np.cos(2*x)),color=M,stroke_width=1))
        self.play(LaggedStart(*[Create(x) for x in markers],lag_ratio=.1),run_time=1.3)
        mean=axes.plot(lambda x:.1*np.sin(x)+.06*np.cos(2*x),x_range=[0,8],color=Y,stroke_width=4)
        self.say('Blending can cancel some errors. It does not guarantee an improvement.')
        self.play(TransformFromCopy(a,mean),b.animate.set_stroke(opacity=.3),a.animate.set_stroke(opacity=.3),FadeOut(markers),run_time=2)
        formula=serif('Different errors  +  honest validation  =  a useful candidate',26,Y).move_to(DOWN*2.15)
        self.play(Write(formula),run_time=1.2)
        self.say('Keep the blend only if held-out checks support it. Curves are illustrative.')
        self.wait(1.4)
        self.play(FadeOut(mean),a.animate.set_stroke(opacity=1),b.animate.set_stroke(opacity=1),run_time=1.2)
        self.say('Single-model quality and ensemble contribution are different questions.')
        self.finish()
