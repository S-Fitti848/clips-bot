# Borrador de la respuesta a YouTube (en inglés)

**Asunto:** Re: YouTube API Services audit – Clips Bot – screencast and step-by-step script

---

Hello,

Thank you for reviewing our application. As requested, here are:

1. **An English screencast** (unlisted on YouTube): https://youtu.be/zlLOnuSHzQc — it shows the full
   flow on our channel (Roty, channel ID UCz0-X39ylB_BAO_yFCLMS8w): how a video is approved, uploaded and scheduled, how we manage it
   (list and cancel the scheduled publication), how we track analytics, and how we perform public
   searches, including the end results in YouTube Studio.
2. **A step-by-step script** ("Clips Bot – API usage walkthrough", attached PDF) with one screenshot per step
   and the exact API method used in each step.

Summary of how Clips Bot uses the YouTube API Services:

- **Upload and schedule:** after the channel owner approves a video in a private Telegram chat, the
  bot calls `videos.insert` (resumable upload) with `privacyStatus=private` and a `publishAt` time.
  Nothing is uploaded without the owner's approval.
- **Manage:** the bot lists the uploads it scheduled and can cancel a scheduled publication with
  `videos.update` (`part=status`, private, no `publishAt`). The video stays private in Studio.
- **Analytics (own channel only):** `channels.list` (mine=true) and `playlistItems.list` to list the
  channel's uploads, and the YouTube Analytics API `reports.query` (views, averageViewDuration,
  averageViewPercentage, audienceWatchRatio) to see how each Short performs.
- **Public search:** `search.list` (type=video, videoDuration=short, order=viewCount) and
  `videos.list` (snippet, statistics, contentDetails), with an API key, to find public Shorts that
  mention the creators we work with and their view counts. Only public data is used (title, channel
  name, view count), only to find which moments became popular, and it is deleted after 30 days.

Clips Bot is a personal tool used only by the channel owner. It only accesses the owner's own channel
through OAuth. Statistics are refreshed before 30 days and deleted if a video no longer exists or
access is revoked. Our privacy policy and terms are at https://s-fitti848.github.io/privacidad.html
and https://s-fitti848.github.io/terminos.html.

Note: since the project is not yet audited, the test video uploaded in the screencast remains private,
as expected.

Please let us know if you need anything else.

Best regards,
Santiago Fittipaldi
rotypro8@gmail.com
