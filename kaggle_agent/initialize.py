"""Safe Windows initializer; existing folders are never overwritten."""
import argparse
import os
from pathlib import Path
import sys


def initialize(parent,name,url="",*,shared=None,automation=False):
    if not name or Path(name).name!=name or name in {".",".."} or any(c in name for c in '<>:"/\\|?*'):
        raise ValueError("Use a single folder name (spaces allowed)")
    parent=Path(parent).resolve();target=parent/name
    target.mkdir()
    shared=Path(shared or Path(__file__).resolve().parents[1])
    relative=os.path.relpath(shared,target).replace("\\","/")
    (target/"AGENTS.md").write_text(f"# {name} Kaggle competition\n\nAt the start of every session, read {relative}/rules.md in full and follow it. Ignore _backups/.\n\n## This competition\n- URL: {url}\n- Notes live in STATE.md and the experiment log.\n",encoding="utf-8")
    # No @import of rules.md: it would auto-load the loop rules into supervised one-script sessions.
    (target/"CLAUDE.md").write_text("@AGENTS.md\n",encoding="utf-8")
    if automation:
        from kaggle_agent.__main__ import init
        init(target,"classification")
    return target


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("name");parser.add_argument("url",nargs="?",default="")
    parser.add_argument("--automation",action="store_true")
    args=parser.parse_args()
    shared=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(shared))
    try:
        target=initialize(shared.parent,args.name,args.url,shared=shared,automation=args.automation)
    except (OSError,ValueError) as error:
        print(str(error),file=sys.stderr);return 1
    print(f"Created {target}\nNext: open Claude Code or Codex in that folder and say: start")
    return 0


if __name__=="__main__":raise SystemExit(main())
