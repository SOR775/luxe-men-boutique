# Backup first
Copy-Item .\static\css\input.css .\static\css\input.css.bak

# Retheme pass: swap every gold/neutral hex used by the custom design
# system (in :root vars and decorative classes like .nav-link:after,
# .footer-link:after, .site-preloader, .glass, .card, etc.) for the
# new pale-green + forest-green palette. Alpha-suffixed hex values
# (e.g. #c8a24c29) are handled automatically since -replace matches
# the leading 6 digits and leaves the trailing alpha suffix intact.
#
#   #c8a24c -> #1f5d3a   primary gold accent      -> deep forest green
#   #d4af37 -> #2f7c4e   secondary gold accent    -> muted forest green
#   #111827 -> #0f1b13   dark text / secondary    -> near-black green
#   #f8fafc -> #f0f7f1   light bg / secondary-lt  -> pale green
#   #050505 -> #0a140d   dark mode bg             -> deep green-black
#   #1f2937 -> #16241b   luxe-gray                -> dark green-gray
#   #6b7280 -> #5c7a68   secondary-soft text      -> muted sage
#   #9ca3af -> #8ba396   muted text               -> light sage-gray
#   #8a7142 -> #4a6b55   preloader tagline        -> muted sage-green
#   #fafafa -> #f0f7f1   preloader bg (light)     -> pale green
#   #0f0f0f -> #10231a   dark surfaces            -> dark green surface
#   #1c1c1c -> #182a20   dark soft-card/preloader -> dark green-gray

$content = Get-Content .\static\css\input.css -Raw
$content = $content -replace '#c8a24c', '#1f5d3a'
$content = $content -replace '#d4af37', '#2f7c4e'
$content = $content -replace '#111827', '#0f1b13'
$content = $content -replace '#f8fafc', '#f0f7f1'
$content = $content -replace '#050505', '#0a140d'
$content = $content -replace '#1f2937', '#16241b'
$content = $content -replace '#6b7280', '#5c7a68'
$content = $content -replace '#9ca3af', '#8ba396'
$content = $content -replace '#8a7142', '#4a6b55'
$content = $content -replace '#fafafa', '#f0f7f1'
$content = $content -replace '#0f0f0f', '#10231a'
$content = $content -replace '#1c1c1c', '#182a20'
Set-Content .\static\css\input.css -Value $content

Write-Host "Done. Backup saved as input.css.bak"
Write-Host "To review exactly what changed, run:"
Write-Host "Compare-Object (Get-Content .\static\css\input.css.bak) (Get-Content .\static\css\input.css)"