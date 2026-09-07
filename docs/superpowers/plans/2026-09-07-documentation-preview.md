# mdx-cli documentation preview

User-approved direction: Japanese documentation for existing portal users, no homepage or photos, explicit unofficial status, navy/blue/lime styling, local browser preview before publishing.

- [x] Reuse the installed Markdown renderer; no local package installation.
- [x] Author Markdown guides under pages/content and render a static multi-page site with relative URLs under pages/_site.
- [x] Add responsive navigation, page outlines, search, code copying and GitHub Pages workflow.
- [x] Build, check local links and command help, and open a localhost preview.

Existing changes in src/mdx_cli/commands/auth.py are outside this task. Deployment will be available as a manually triggered workflow; this preview does not publish the site.

Validation: 12 pages built; 287 local links, assets and anchors checked; browser preview and OTP search verified. VPN requirement removed from guides and README following user correction.
