// Cert Finder settings, shared by index.html and stats.html.
//
// statsApiUrl (live results counter, optional)
//   ""       -> stats off. Current setting: the site is hosted on Vercel and the
//               AWS backend isn't deployed yet. The quiz works fully without it.
//   "https://<id>.lambda-url.<region>.on.aws/" -> after deploying the AWS stack
//               (docs/DEPLOY.md), use its StatsApiUrl output here.
//   "/api/"  -> when the site itself runs on the AWS CloudFront setup, or locally
//               with scripts/dev_server.py.
// If the API isn't reachable the quiz still works; it just doesn't count.
window.CERT_FINDER_CONFIG = {
  statsApiUrl: "https://rp6gz532fawwxd5hegreo3sh4q0ncfev.lambda-url.eu-north-1.on.aws/",
  treeUrl: "data/tree.json"
};
