# RUN THIS AFTER the previous retheme_input_css.ps1 script.
# That script already converted input.css from gold -> forest green.
# This second pass converts forest green -> neon lime + adds the
# dark-mode gradient, matching the reference mobile-app mockup.

Copy-Item .\static\css\input.css .\static\css\input.css.bak2

$content = Get-Content .\static\css\input.css -Raw

# Accent: forest green -> bright neon lime
#   #1f5d3a -> #8ce93b   primary accent (was deep forest green)
#   #2f7c4e -> #a6f24d   accent hover/muted (brighter lime, since hovers
#                        brighten on a dark background rather than darken)
$content = $content -replace '#1f5d3a', '#8ce93b'
$content = $content -replace '#2f7c4e', '#a6f24d'

# Dark mode backgrounds: flat dark green -> gradient-friendly near-black,
# plus a new gradient-start green for use on body/hero backgrounds.
#   #0a140d -> #070d08   dark bg (gradient END)
$content = $content -replace '#0a140d', '#070d08'

Set-Content .\static\css\input.css -Value $content

# Add the gradient-start color and a reusable gradient class directly,
# since raw CSS variables aren't affected by Tailwind's config at all.
Add-Content .\static\css\input.css @"

/* RETHEME v2: dark green gradient background + neon lime accent,
   matching the reference mobile-app mockup design. */
:root {
  --color-luxe-dark-start: #173c22;
}
.dark body {
  background: linear-gradient(135deg, var(--color-luxe-dark-start), var(--color-luxe-dark));
  background-attachment: fixed;
}
"@

Write-Host "Done. Backups saved as input.css.bak (pass 1) and input.css.bak2 (pass 2)."
Write-Host "Next: run 'npm run build:css', then hard-refresh / use incognito to test."