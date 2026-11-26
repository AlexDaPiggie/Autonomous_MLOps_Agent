# Rebuilding the README GIFs

The seven GIFs are embedded directly in the README. The explanatory diagrams use Manim Community; the mock setup uses a scripted terminal renderer. The setup recording does not execute any displayed command or capture the user's desktop.

```powershell
python -m pip install manim Pillow
# Make ffmpeg available on PATH.
python docs/tools/render_readme.py
python docs/tools/render_setup.py
```

To revise just one diagram: `python docs/tools/render_readme.py Ensemble` (also Budget, Supervisor, Search, Memory, Validation). The renderer stages GIFs before replacing the final assets; temporary videos are discarded.

- [Research and precise source links](../ANIMATION_RESEARCH.md)
- [Visual scripts and review gates](../ANIMATION_STORYBOARD.md)
- `readme_scenes.py`: geometry, transitions, local labels, and timing.
- `render_readme.py`: 1024×576 vector render and looping 20 fps GIF export.
- `render_setup.py`: mock PowerShell commands, typing, condensed example output, and 16 fps export.

The revised direction is graphite, warm white, gray, and one muted accent. Filled/open markers, hatching, row identity, and position explain the relationships independently of color. Scene content is illustrative, with no fabricated competition scores or measured performance claims. Font choices are Segoe UI and Consolas; substitute installed fonts on non-Windows systems.

3Blue1Brown's own guidance informed the visual storytelling, rather than supplying assets or a claimed official palette. The source evidence and our design judgments are separated in the research note.
