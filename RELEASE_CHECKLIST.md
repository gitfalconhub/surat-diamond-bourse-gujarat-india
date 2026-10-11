# Surat Diamond Bourse release checks

Run these checks on the exact files that will be published, including repository history and every release ZIP. Record the commit, hashes, date, results, and anything that was not checked.

1. Use GitHub's private `noreply` commit email. Inspect author and committer emails across every published branch and tag. Keep email privacy and email-exposure push blocking enabled.
2. Scan all reachable Git history and staged files for credentials. Review findings manually. Inspect binary assets separately; a clean source scanner does not establish that binary files are private.
3. Inspect PNG text/EXIF/XMP metadata and other image metadata. Remove personal usernames, local paths, account details, and unnecessary timestamps without changing pixels or deleting required attribution.
4. Open `.blend` files in a separate Blender process with factory preferences and automatic script execution disabled. Inspect every text block, Python auto-run flag, driver, script node, external dependency, custom property, saved browser directory, and console history.
5. Include only public documentation in Blender files. Keep production handoffs, account/usage notes, correspondence, research scratch files, and old execution runners out of downloadable files. Ship reviewed scripts in the separate `scripts/` directory.
6. Scan decompressed Blender contents for personal paths and credentials. Reopen cleaned files and verify geometry, object hierarchy, materials, packed textures, animation curves, camera markers, and presentation settings.
7. Review script file writes and scene deletion. Test in a disposable directory and scene. Scripts should refuse unexpected overwrites, keep outputs inside the project, create required directories, and fail clearly when required inputs are absent.
8. Assemble ZIPs from an explicit allowlist. Reject absolute paths, parent traversal, symbolic links, `.git`, `.env`, private keys, backups, logs, and working directories. Verify archive CRC and advertised checksums.
9. Check GitHub account authentication, collaborators, deploy keys, installed apps, branch/tag rules, scanning, and release integrity. Grant only necessary access. Finish any required history cleanup before preventing force pushes or freezing releases.
10. Verify the actual published branch, tags, source archives, release downloads, and hashes after publication. A local clean package is not evidence of a completed public cleanup.

History rewriting cannot recall previous downloads or clones. Old commit URLs and caches may remain available; assess those separately when removing previously published information.
