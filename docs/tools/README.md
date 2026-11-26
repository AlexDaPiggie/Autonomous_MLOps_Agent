# Rebuilding the README animations

These are scripted vector animations made with Manim Community, exported as looping GIFs.

```powershell
python -m pip install manim
# Install ffmpeg and make it available on PATH, then:
python docs/tools/render_readme.py
```

The renderer writes six GIFs to `docs/assets/`. Intermediate videos go into a temporary directory. `readme_scenes.py` contains the diagram geometry, transformations, timing, and captions. Windows uses Cambria and Segoe UI fonts; substitute installed fonts on other systems.

The visual reference is [3Blue1Brown](https://www.3blue1brown.com/): a dark mathematical canvas, restrained color, progressive construction, and transformations that explain relationships. These are original project diagrams, not 3Blue1Brown assets or an affiliated production.
