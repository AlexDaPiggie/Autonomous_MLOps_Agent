"""Render a scripted mock PowerShell screencast. No displayed command is executed.
Run: python docs/tools/render_setup.py
Requires Pillow and ffmpeg. No user files, screens, credentials, or accounts are captured.
"""
from pathlib import Path
import math,subprocess,tempfile
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/assets/00-setup.gif'
W,H=1120,650;FPS=20;BG='#151515';INK='#e6e3dd';GRAY='#969696';DIM='#505050';ACCENT='#b6a6cd'
FONTS=Path('C:/Windows/Fonts')
mono=ImageFont.truetype(str(FONTS/'consola.ttf'),21)
small=ImageFont.truetype(str(FONTS/'segoeui.ttf'),17)
head=ImageFont.truetype(str(FONTS/'segoeui.ttf'),29)
SCREENS=[
 ('01 / Get the project','First install Python 3.11+, Git, and your chosen agent CLI.',
 [('git clone https://github.com/AlexDaPiggie/Agent_Loop_For_Kaggle.git `\n  _kaggle_shared',['[demo] Repository copied into _kaggle_shared.']),('cd _kaggle_shared',[])],5.6),
 ('02 / Install the package','Use the same Python for installation and for running ka.',
 [('python -m pip install -e ".[models]" kaggle',['[demo] Installing project and model dependencies ...','[demo] Installed. The ka command is now available.'])],4.5),
 ('03 / Sign in','For Claude instead: run claude, then /login in its terminal.',
 [('codex login',['[demo] Complete account sign-in in your browser.','[demo] No account or sign-in action happens in this recording.'])],4),
 ('04 / Configure a small run','Example limits below; choose values your computer can support.',
 [('ka setup',['[demo, abridged prompts]','Agent: codex       Model: <Enter for CLI default>','Effort: <Enter>    CPU threads: 2    Memory: 2048 MB','Max hours per run: 0.5','Campaigns: 1       Trials: 2         Phone alerts: none','Save these? y','[demo] Saved. Next: ka new <competition URL>'])],7),
 ('05 / Create the competition','Create Kaggle credentials; join and accept its rules on Kaggle first.',
 [('ka new https://www.kaggle.com/competitions/YOUR-COMPETITION',['[demo] Check the detected columns and metric when prompted.','[demo] Confirm rules reviewed; choose NO for auto-submit.'])],5),
 ('06 / Run two trials','YOUR-COMPETITION is a placeholder. Use the slug from your Kaggle URL.',
 [(r'cd ..\YOUR-COMPETITION',[]),('ka go --campaigns 1 --trials 2',['[demo] Trial 1/2: agent writes an experiment; supervisor tests it.','[demo] Inspect results with ka status or ka dash.'])],5.5),
]
def wrap(s,d,width=1008):
 lines=[];part=''
 for ch in s:
  if ch=='\n':lines.append(part);part='  ';continue
  if d.textlength(part+ch,font=mono)>width:lines.append(part);part='    '+ch
  else:part+=ch
 return lines+[part]
def render(screen,t,duration):
 title,note,commands,_=screen
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
 d.text((42,23),'MOCK SETUP  /  POWERSHELL',font=small,fill=GRAY)
 d.text((W-42,23),'SIMULATED · NO COMMANDS EXECUTED',font=small,fill=GRAY,anchor='ra')
 d.text((42,66),title,font=head,fill=INK);d.line((42,114,W-42,114),fill=DIM,width=1)
 # Reveal each command in order, then its condensed mock output. Never execute shell text.
 times=[];cursor=.25
 for command,outputs in commands:
  typing=max(.5,len(command)/52);times.append((cursor,typing,command,outputs));cursor+=typing+max(.55,len(outputs)*.34)+.45
 scale=min(1,(duration-1.1)/max(cursor,.1));tt=t/scale
 lines=[];active=None
 for start,typing,command,outputs in times:
  if tt<start:break
  shown=command[:min(len(command),int((tt-start)/typing*len(command)))];full=tt>=start+typing
  for part in wrap('PS> '+shown,d):lines.append((part,INK))
  if not full:active=len(lines)-1;break
  for j,out in enumerate(outputs):
   if tt>=start+typing+.2+j*.34:
    for part in wrap(out,d):lines.append((part,GRAY))
  if tt<start+typing+.2+len(outputs)*.34+.2:break
  lines.append(('',GRAY))
 maxlines=13
 if len(lines)>maxlines:lines=lines[-maxlines:]
 for i,(s,col) in enumerate(lines):d.text((42,139+i*29),s,font=mono,fill=col)
 if active is not None and int(t*3)%2==0 and lines:
  s=lines[-1][0];x=42+d.textlength(s,font=mono);y=139+(len(lines)-1)*29;d.rectangle((x+2,y+2,x+4,y+24),fill=ACCENT)
 d.line((42,H-86,W-42,H-86),fill=DIM,width=1)
 d.text((42,H-64),note,font=small,fill=INK)
 d.text((42,H-33),'Read the commands and account prerequisites below this GIF.',font=small,fill=GRAY)
 d.rectangle((0,H-3,int(W*t/duration),H),fill=ACCENT)
 return im
with tempfile.TemporaryDirectory(prefix='ka-setup-demo-') as temp:
 video=Path(temp)/'setup.mp4'
 command=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','20',str(video)]
 with subprocess.Popen(command,stdin=subprocess.PIPE) as proc:
  for screen in SCREENS:
   duration=screen[-1]
   for i in range(round(duration*FPS)):proc.stdin.write(render(screen,i/FPS,duration).tobytes())
  proc.stdin.close()
  if proc.wait():raise RuntimeError('Video encoding failed')
 staged=Path(temp)/'setup.gif'
 subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-filter_complex','fps=16,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none','-loop','0',str(staged)],check=True)
 staged.replace(OUT)
print(f'Mock setup GIF: {OUT.stat().st_size//1024} KiB')
