# Spotter, the ThoughtSpot mascot

`Spotter.h2m-character.zip` is a ready-made [character](../../docs/characters.md): a Pixar-style 3D puppy in teal armour that talks and acts in
your videos. It holds his picture (idle and talking loops), five action clips (wave, wink, laugh, think, wag), the cut-out they were made from
and his voice setting (Puppy).

## Use him

1. Start the Studio (`./studio.sh`) on a version that has characters (the `spotter-actor` branch, or `main` once it is merged).
2. **Settings > Media library > Import a character** and choose `Spotter.h2m-character.zip`.
   From a terminal instead: `curl -s -F "file=@examples/characters/Spotter.h2m-character.zip" http://127.0.0.1:8765/api/media/import`
3. In any script:

```
Title: Meet Spotter
## Hello
Say: Welcome to the show.
Spotter animate: wave
Spotter say: Hi, I'm Spotter!
Spotter animate: wink
```

He is placed on every slide where he speaks or acts. His words are heard, not printed (use `Spotter bubble: …` to print them too). Besides
the clips he can jump, hop, nod, shake, bounce, wiggle and spin. See [Characters](../../docs/characters.md) for the full list of words and how to
make a character of your own.

Importing never overwrites anything: if you already have a character called Spotter, the copy is "Spotter (2)".
