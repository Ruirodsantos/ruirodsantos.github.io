---
layout: default
title: "Subscribe to AI Pulse — Free Daily AI Newsletter"
description: "Get the most important AI news every morning, explained simply. Free forever. No spam."
permalink: /subscribe/
---
<div class="page-wrap" style="max-width:600px;margin:0 auto;padding:60px 20px;text-align:center">
  <p style="font-size:40px;margin:0 0 16px">📬</p>
  <h1 style="font-size:32px;font-weight:800;color:var(--navy);margin:0 0 12px">Stay ahead of AI</h1>
  <p style="font-size:16px;color:#666;line-height:1.7;margin:0 0 32px">Every morning, get the most important AI stories of the day — explained in plain English. No jargon, no hype. Just what actually matters for your work and money.</p>
  
  <div style="background:#f8f9fa;border-radius:12px;padding:28px;margin-bottom:32px">
    <form style="display:flex;flex-direction:column;gap:12px;max-width:360px;margin:0 auto" onsubmit="handleSubscribe(event)">
      <input type="email" id="sub-email" placeholder="your@email.com" required style="padding:12px 18px;border-radius:8px;border:1.5px solid #e0e0e0;font-size:15px;text-align:center"/>
      <button type="submit" style="padding:14px;background:#180d3c;color:#fff;font-size:15px;font-weight:700;border:none;border-radius:8px;cursor:pointer">Subscribe free →</button>
    </form>
    <p style="font-size:12px;color:#aaa;margin:12px 0 0">No spam. Unsubscribe anytime. Free forever.</p>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;text-align:center">
    <div style="padding:16px;background:#fff;border-radius:8px;border:1px solid #eee">
      <p style="font-size:24px;margin:0 0 4px">📅</p>
      <p style="font-size:13px;font-weight:700;color:var(--navy);margin:0 0 4px">Daily</p>
      <p style="font-size:12px;color:#888;margin:0">Every morning, 7am</p>
    </div>
    <div style="padding:16px;background:#fff;border-radius:8px;border:1px solid #eee">
      <p style="font-size:24px;margin:0 0 4px">✂️</p>
      <p style="font-size:13px;font-weight:700;color:var(--navy);margin:0 0 4px">Curated</p>
      <p style="font-size:12px;color:#888;margin:0">Only what matters</p>
    </div>
    <div style="padding:16px;background:#fff;border-radius:8px;border:1px solid #eee">
      <p style="font-size:24px;margin:0 0 4px">🆓</p>
      <p style="font-size:13px;font-weight:700;color:var(--navy);margin:0 0 4px">Free</p>
      <p style="font-size:12px;color:#888;margin:0">Always free</p>
    </div>
  </div>
</div>

<script>
function handleSubscribe(e){
  e.preventDefault();
  const email = document.getElementById('sub-email').value;
  // Redirect to Beehiiv/Mailchimp — update this URL when you connect a provider
  window.location.href = 'https://aipulse.beehiiv.com/subscribe?email=' + encodeURIComponent(email);
}
</script>
