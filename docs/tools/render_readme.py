"""Build the six README GIFs; output videos/intermediates stay in a temp folder.
Requires: pip install manim; ffmpeg on PATH. Run from any directory.
"""
from pathlib import Path
import subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
SCENES={'Budget':'01-budget','Supervisor':'02-supervisor','Search':'03-search','Memory':'04-memory','Validation':'05-validation','Ensemble':'06-ensemble'}
SCENES={k:v for k,v in SCENES.items() if not sys.argv[1:] or k in sys.argv[1:]}
with tempfile.TemporaryDirectory(prefix='kaggle-readme-animation-') as temp:
    subprocess.run([sys.executable,'-m','manim','--disable_caching','--verbosity','ERROR','--progress_bar','none','--media_dir',temp,'-r','1024,576','--fps','30',str(ROOT/'docs/tools/readme_scenes.py'),*SCENES],check=True)
    for scene,name in SCENES.items():
        video=next(Path(temp).rglob(scene+'.mp4'))
        out=ROOT/'docs/assets'/f'{name}.gif'
        staged=Path(temp)/f'{name}.gif'
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-filter_complex','fps=20,split[a][b];[a]palettegen=max_colors=128:stats_mode=full[p];[b][p]paletteuse=dither=none','-loop','0',str(staged)],check=True)
        staged.replace(out)
        print(f'{name}: {out.stat().st_size/1024:.0f} KiB',flush=True)
print('README GIFs rendered.')
