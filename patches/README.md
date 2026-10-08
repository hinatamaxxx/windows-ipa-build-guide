# Moonlight scene lifecycle patch

`moonlight-scene-lifecycle.patch` adapts Moonlight's existing UIKit app to a
single UIWindowScene, retaining its iPhone/iPad storyboards and shortcut state.
It targets moonlight-stream/moonlight-ios commit
`02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a`.

This patch contains context from Moonlight and is distributed under GNU GPL v3,
not the MIT license covering the guide's independent helper scripts. See
[LICENSE-Moonlight.txt](LICENSE-Moonlight.txt). The resource kit retains the
upstream license as well.

Modification date: 2026-10-08. No Tailscale implementation is included here.
