import json
from pathlib import Path

data=[]
def add(id,title,author,url,kind,summary,entries,compute='Local rendering and inspection; no model training is needed.',limits='',related=None):
    source_title=title
    findings=[]
    for title,q,loc,meaning,application,strengths,limitations,action in entries:
        findings.append(dict(title=title,quote=q,locator=loc,meaning=meaning,application=application,strengths=strengths,limitations=limitations,action=action))
    data.append(dict(id=id,title=source_title,authors=author,url=url,kind=kind,locator='Specific locations below',identity_status='Verified primary text',summary=summary,findings=findings,compute=dict(training=compute,agent_inference='Authoring may use the selected coding assistant; this source does not establish a comparable inference budget.',observed_budget='No transferable monetary benchmark verified.',caveat='Design advice is not evidence of improved competition performance.'),evidence_limits=limits,related_links=related or []))

add('visual-faq','Sanderson creator advice','Grant Sanderson','https://www.3blue1brown.com/about/','First party creator FAQ',
    'The useful transfer is a visual explanation method rather than a recognizable palette. The FAQ recommends concrete examples and purposeful movement.',[
    ('Start with a concrete discrepancy','Concrete before abstract.','FAQs → I would like to start making math videos online → second bullet',
     'Sanderson recommends examples before general frameworks. This is creator guidance, not a controlled study of developer documentation.',
     'Open the supervisor GIF on four prediction rows facing five expected IDs. Let the empty slot become visible before naming validation. Open search on a growing frontier before showing its cap. The viewer then has a reason for a controller or portfolio instead of memorizing component names. These examples should follow real output and branch contracts in loop.py and research/branches.py.',
     'A small CPU example can demonstrate a real project invariant without training a new model.',
     'Simplification can hide repair limits or imply every failure is recoverable. A convincing diagram does not establish comprehension or prove the underlying pipeline is correct.',
     'Ask a newcomer to explain why the candidate cannot reach scoring without reading a caption that supplies the answer.'),
    ('Animate the relationship rather than the prose','Every movement on the screen should be deliberate','FAQs → creator advice → Avoid pointless animations bullet',
     'The advice rejects movement with no identifiable explanatory purpose. It does not ask for constant motion or prescribe a universal animation frequency.',
     'Give every self.play call in readme_scenes.py a state transition to communicate. A result moving back represents repair; aligned residuals converging represents averaging. Keep unchanged evidence stationary while the selected object changes. Remove pulsing labels or moving equations that merely decorate the screen. Retain a short hold after a difficult inference.',
     'This produces a review criterion that works locally and can reduce scene complexity.',
     'Purpose depends on audience knowledge. Silent GIFs lack spoken pacing cues, and fast movement may conceal the very comparison the viewer needs to inspect.',
     'Maintain a beat list with visible change and intended inference. Revise beats whose only contribution is a sentence appearing.')],
    limits='The linked creator videos were located, but original video frames were not reviewed. No official Sanderson palette or universal comprehension recipe is claimed.',
    related=['https://www.youtube.com/watch?v=ojjzXyQCzso','https://www.3blue1brown.com/lessons/some1/'])

add('visual-grace','Iterating the script against the animation','Grant Sanderson interviewed by Grace Gong','https://gracegong.beehiiv.com/p/makes-content-stick-ft-3blue1brown-channels-creator-grant-sanderson-493-million-subscribers-yt','Firsthand interview edited for reading',
    'The host says the text is adapted from an interview. The useful finding is that writing, visual construction, and revision inform one another.',[
    ('A weak visual can expose a weak explanation','If the animation is not visually compelling','Question Your teaching style is unique and captivating → GS answer',
     'The surrounding answer connects a visual problem to restructuring the explanation. The quoted phrase alone should not be treated as a complete production rule.',
     'Replace generic sinusoid curves with residual samples aligned to the same held-out row, then show their midpoint. That changes what the diagram explains, not just its appearance. When a scene feels generic, revise its example and object relationships before adding transitions. The same discipline helps architecture work: an incoherent data-flow picture is a reason to inspect the design.',
     'The idea directs work toward semantic content and fits deterministic, code-generated diagrams.',
     'Visual appeal is not correctness. An attractive midpoint can hide unequal weights, mismatched prediction scales, missing IDs, or leakage.',
     'Check one numerical residual pair before rendering the whole scene; preserve originals alongside the derived mean.'),
    ('Rendered evidence should change the script','make adjustments after seeing the animation','Question Do you write a script for the animation and narration → GS answer',
     'The published answer describes the narration script as a revisable guide. It does not supply fixed scene durations or a palette.',
     'Keep the storyboard beside the scene code and review before, transition, and after frames. If a label collides with a moving object, change the path or script instead of shrinking everything. Render a representative hard scene before rebuilding all assets. For agent briefs, likewise inspect whether the evidence is actually communicated, while leaving frozen scoring contracts unchanged.',
     'Small, reviewable iterations can avoid rebuilding unrelated scenes.',
     'Rendering and inspection still consume CPU time and human attention. The interview does not establish the best budget allocation for our documentation.',
     'Record why a scene changed and rebuild only the affected scene until its central transition is clear.')],
    limits='The publisher explicitly says parts were adjusted for reading; quotations are from that edited text, not a certified verbatim recording.')

add('visual-roganov','Object transformations and production planning','Grant Sanderson interviewed by Ivan Roganov','https://roganov.me/blog/3blue1brown-interview/','Firsthand written interview',
    'The interviewer identifies a Q and A originally published for Habr readers. It discusses object transformations and variable script development time.',[
    ('Preserve object identity through a transition','creating animations of object transformations','Question How and why did you create your YouTube channel → answer',
     'Sanderson describes the original purpose of Manim. This supports continuity as a production technique, not a requirement to transform everything.',
     'Keep an output row identifiable as it enters a contract check and returns for repair. Keep stored records visible while a selection becomes a brief. Keep residual pairs attached to the same row as their mean is computed. These are pictures of this project’s actual concerns: record identity, evidence persistence, and aligned predictions.',
     'The existing renderer can express these relationships without a paid inference or training experiment.',
     'A transformation can falsely imply equivalence. A summary is not its complete evidence, and a residual average is not a newly trained independent model.',
     'Label derived objects and originals separately; identify the data or arithmetic contract behind each transformation.'),
    ('Separate planning from rendering effort','Sometimes it takes 3 months.','Question How long does it take to write a script → first answer paragraph',
     'This is a dated personal account of variation in script writing, not a schedule for our short GIFs.',
     'Separate deciding what the scene must explain from rendering it. Write one acceptance question, then iterate the question against a draft before polishing every asset. Apply the same discipline to research: representation work may be valuable, but it still needs a bounded experiment and stop condition. Creative uncertainty does not authorize endless agent activity.',
     'It prevents a fast render from being mistaken for a completed explanation.',
     'The anecdote cannot justify weeks of documentation work while reliability or scoring defects remain unresolved.',
     'Timebox a draft and review cycle; prioritize defects that prevent understanding rather than indefinite stylistic refinements.')],
    limits='Published December 9 2021. This is an interview account, not a production-time benchmark.')

add('visual-workflow','Sanderson implementation workflow and version compatibility','Grant Sanderson and contributors','https://github.com/3b1b/videos','First party source repository README',
    'The official repository distinguishes the creator’s engine from Manim Community and describes restoring interactive scene state. The README, not unseen demonstration footage, is the quoted evidence.',[
    ('Similar engine names do not ensure identical behavior','some functionality may differ between the two.','README → Workflow → opening paragraph',
     'A technique demonstrated in the creator’s environment may not run unchanged in Manim Community.',
     'Our scene code imports Manim Community. Record the verified version, fonts, ffmpeg settings, dimensions, and frame rate. Borrow the production principle rather than copying creator-specific commands. Test output decoding after dependency changes, much as the experiment system retains code and evaluator identity alongside scored artifacts.',
     'Compatibility checks are cheap and reinforce reproducibility.',
     'Fonts and rendering dependencies can change despite a Python version pin. The engine and finished scenes also have different licensing contexts; copying a scene needs a separate license check.',
     'Rerender one representative scene after a dependency change and compare its key frames and decoded output.'),
    ('Focused state restoration supports iteration','will first revert to that state of the scene','README → Workflow → checkpoint_paste bullet',
     'The creator’s interactive workflow restores a saved scene state before replaying a changed fragment.',
     'Keep a known before state for difficult transitions and revise that fragment instead of rebuilding unrelated scenes. Borrow the general principle for development, but distinguish it from crash-safe experiment persistence. The Kaggle controller still requires durable job identity, checksums, and reconciliation; a visual scene checkpoint provides none of those guarantees.',
     'Focused iteration reduces unrelated rebuild work and narrows a visual failure.',
     'checkpoint_paste is not implemented by our helper. Similar ideas at different abstraction levels must not be presented as equivalent mechanisms.',
     'Use the per-scene renderer selector and retain a small transition example when diagnosing layout problems.')],
    limits='The README was read. The linked official YouTube demonstration was found; no timing or color claims rely on unobserved video frames.',
    related=['https://www.youtube.com/watch?v=rbu7Zu5X1zI'])

add('visual-forum','A creator workflow for storyboards and timing','u/purplemindcs','https://www.reddit.com/r/manim/comments/1g3lsc0/episode_3_of_brainstorm_collaborative_mathematics/','Firsthand practitioner forum comment',
    'The creator describes a production sequence in response to another user. This is useful practice evidence, not Sanderson’s statement or a controlled study.',[
    ('Storyboarding reveals missing explanatory steps','Make a storyboard.','Reply to u/faizalHoonBC → numbered process → item 3',
     'The creator describes sketching defining scene elements before animation.',
     'Write a visible problem, objects, transition, and inference for each beat. In setup, separate browser account prerequisites from terminal commands; simulated terminal output must not pretend to complete real sign-in. For architecture, storyboard the missing row before writing movement paths. This keeps the GIF from becoming another list of component names.',
     'A small Markdown storyboard fits the repository and is easy to review.',
     'A storyboard can lock in a bad explanation if treated as final. The comment also supports experimentation and timing adjustments.',
     'Review each beat against the actual code contract before rendering; remove any inference the objects cannot show.'),
    ('Timing needs a later inspection pass','add some freeze frames or cut out wait time','Same creator reply → process item 4',
     'The commenter adjusts timing after animating. No universal hold duration follows from that account.',
     'Review the actual silent GIF at normal playback speed. Leave time to notice a mismatch and read a local label, then let the geometry do the next step. In setup, long commands and condensed prompts need recognition time. Keep all essential instructions in static, copyable text below the recording.',
     'Timing can improve clarity without more effects or colors.',
     'Readers have different familiarity and GIF players do not provide consistent pause or seek controls.',
     'Inspect the busiest frame and ensure no critical setup instruction exists only in moving text.')],
    limits='The commenter is the creator of the posted work, not Grant Sanderson. A personal workflow does not establish comparative effectiveness.')

add('visual-color','A neutral palette with intentional emphasis','IBM Design Language','https://www.ibm.com/design/language/color/','First party design guidance',
    'IBM supports neutral organization and purposeful additional color. Its own brand has a core blue; our palette is an adaptation to this user’s feedback, not an official IBM or Sanderson palette.',[
    ('Neutral context can organize the scene','The neutral gray family is dominant in our UI','Color in UI → Specifications → opening paragraph',
     'This rule concerns IBM interfaces; transferring it to technical GIFs is a design judgment.',
     'Use graphite for the canvas, warm white for main marks, and gray for retained context. Shape and position can explain the relationship without a colored card. A single muted accent marks the current operation. In the residual example, filled and open points distinguish models without saturated category colors.',
     'A restrained vector palette supports continuity across all seven GIFs.',
     'Neutral lines can become too faint at GitHub display width. Thin connectors and small row IDs may be illegible despite looking attractive at render resolution.',
     'Check the least contrasted useful element at normal README width before accepting an export.'),
    ('Additional hue should have a defined role','Additional colors are used sparingly and purposefully.','Color in UI → Specifications → final sentence',
     'The guidance favors intentional use rather than a different hue for every object.',
     'Reserve the accent for the selected branch, missing row, or derived mean. Keep unchanged evidence neutral. Where identity matters, first use alignment, marker fill, labels, or line style. A gray-scale check should still reveal the relationship; the accent then guides attention instead of carrying the entire meaning.',
     'A small role vocabulary is easier to maintain and less template-like.',
     'One accent can confuse failure and success if local labels and geometry do not explain the current operation.',
     'Document the accent’s role in each storyboard beat and reject scenes that require naming a hue to explain them.')],
    limits='Direct page fetches timed out; exact official page text was obtained through the search index. Later revisions may alter wording.')

add('visual-diagrams','Identity cues in technical diagrams','IBM Design Language','https://www.ibm.com/design/language/infographics/technical-diagrams/design/','First party technical diagram specification',
    'The specification covers accessibility and coherent node treatment. It informs our encoding; avoiding generic bordered cards is a project-specific choice.',[
    ('Color cannot be the only identity cue','Never rely on color alone to convey meaning.','Color → Color usage → accessibility paragraph',
     'The source requires redundant cues such as labels, line styles, or icons.',
     'Use hatching and row numbers for held-out data, filled and open markers for residual pairs, and a frontier boundary for search. Each distinction survives grayscale. This also helps when GIF quantization changes subtle color values. Keep only the cues needed for the current inference so redundant encoding does not turn into clutter.',
     'The scene remains interpretable across different displays and color perception.',
     'Adding an icon, label, and pattern to every mark can overwhelm a compact scene. Redundancy should protect meaningful distinctions, not maximize decoration.',
     'Inspect a grayscale key frame and identify held-out rows, residual partners, and the selected branch without using color names.'),
    ('Coherent nodes do not require multicolor cards','Nodes should be monochromatic.','Color usage → example caption Don’t mix colors when drawing a node',
     'The statement governs node construction. It neither requires boxes everywhere nor prohibits a meaningful overall palette.',
     'Use rows, points, or line segments when they carry the data relationship directly. Use one ring where a session boundary matters. Keep ownership labels for the agent and scorer even when removing decorative borders. Minimalism is useful only if trust boundaries and data identity remain understandable.',
     'The approach addresses the user’s explicit objection to colored borders.',
     'Removing every boundary can erase the separation between writing and scoring. A simpler picture must retain important architecture distinctions.',
     'Remove a node boundary only when the scene still clearly identifies which component writes code and which accepts evidence.')],
    limits='Official body text and the indexed Color section were inspected. This is a design specification, not proof of improved audience comprehension.')

add('visual-motion','Purposeful motion and easing','Carbon Design System','https://www.carbondesignsystem.com/building-blocks/foundations/motion/overview','First party motion guidance',
    'Carbon distinguishes productive and expressive interface motion. Its UI timings are not an established educational-video pacing standard.',[
    ('Reserve prominent motion for important changes','Reserve expressive motion for occasional, important moments','Style → paragraph after productive and expressive motion',
     'Ordinary operation and important moments should not all compete at the same visual intensity.',
     'Let the missing row, restored validation split, and residual midpoint be focal events. Keep headings and unchanged records still during those transitions. A stable scene structure can support recognition, but the main geometry should be specific to each idea rather than a repeated card sequence.',
     'The viewer has fewer competing motions to track.',
     'Importance depends on audience knowledge. A skilled ML reader and a new project user may need different explanations of aligned predictions.',
     'Ask a reviewer what changed in each beat. If they name an unrelated moving label, simplify the motion.'),
    ('Smooth stopping can preserve object continuity','speed up quickly and slow down smoothly','Easing → opening paragraph',
     'The guidance describes acceleration and deceleration for screen objects, while discouraging purely decorative movement.',
     'Use gentle starts and stops for records moving into checks or briefs entering a session. Use linear movement only when the mark represents a rate or ongoing progression. Residuals must stop at their actual arithmetic midpoint rather than bounce for visual excitement. The endpoint matters more than the flourish.',
     'Manim expresses this directly without new model training.',
     'Easing can misrepresent measured progress or rates. Work-allocation diagrams must remain explicitly illustrative unless they use actual timing data.',
     'Check the endpoint against the intended value, then review the path for misleading overshoot or timing claims.')],
    limits='The page shows an August 2026 update. No exact GIF frame rate or educational-effectiveness claim is attributed to Carbon.')

add('visual-datawrapper','Choose the visual encoding from the information','Lisa Charlotte Muth at Datawrapper','https://www.datawrapper.de/blog/which-color-scale-to-use-in-data-vis','First party visualization article',
    'Position, marker style, and labels can already identify data. The article helps decide when additional color communicates something rather than merely repeating it.',[
    ('Avoid redundant hue when position already identifies data','already encodes the states by position','What to color by → choropleth map paragraph',
     'The source’s example is a map. Applying the principle to residual pairs is our design interpretation.',
     'Place each pair of errors at the same horizontal row coordinate. Distinguish predictors with filled and open marks and place the mean at the midpoint. The picture then explains averaging without red, blue, and yellow curves. For search, a boundary and selection position can identify the relevant frontier without a unique hue for each hypothesis.',
     'Geometry corresponds directly to a data relationship or computation.',
     'Position is insufficient if objects cross or overlap ambiguously. A transition may need a local identity label at its hardest moment.',
     'Trace one residual pair through the full transition and check that its members cannot be mistaken for the neighboring row.'),
    ('Lightness remains important after export','Give your hues different lightnesses','Categorical color scales → first practical bullet',
     'The article recommends distinguishable lightness, including for gray-scale interpretation.',
     'Check main text, secondary labels, and useful connectors against the graphite background. Review the final GIF because palette reduction may change subtle values. Preserve static, copyable commands below the setup demo so a reader does not have to extract a critical instruction from a moving frame.',
     'Export inspection catches failures that source code review cannot reveal.',
     'A gray-scale test does not cover all accessibility needs. Adequate contrast alone cannot make tiny text readable, and GIF playback controls vary by viewer.',
     'Inspect the busiest exported frame at normal display width and keep a text alternative for essential instructions.')],
    limits='This is a visualization article, not a study of the repository or an endorsement of its revised assets.')

Path('docs/research/visual_sources.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Visual dossiers:',len(data))
