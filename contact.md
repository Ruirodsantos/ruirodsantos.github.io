---
layout: default
title: Contact AI Pulse
description: Get in touch with the AI Pulse team. We welcome feedback, suggestions and press enquiries.
permalink: /contact/
---
<div style="max-width:700px;margin:0 auto;padding:40px 16px 80px">
  <nav style="font-size:13px;color:#868e96;margin-bottom:24px"><a href="/" style="color:#41e37a">Home</a> &rsaquo; Contact</nav>
  <h1 style="font-size:32px;font-weight:800;color:#180d3c;margin-bottom:8px;letter-spacing:-.5px">Get in touch</h1>
  <p style="font-size:16px;color:#495057;margin-bottom:40px;padding-bottom:24px;border-bottom:1px solid #e9ecef;line-height:1.6">We'd love to hear from you. Whether you have feedback, a story tip, or a press enquiry, drop us a message below.</p>

  <!-- CONTACT CARDS -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:40px">
    <div style="background:#f8f9fa;border-radius:8px;padding:20px;border-top:3px solid #41e37a">
      <p style="font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#41e37a;margin-bottom:8px">General</p>
      <p style="font-weight:700;color:#180d3c;margin-bottom:4px">Questions &amp; Feedback</p>
      <p style="font-size:13px;color:#495057">Ideas, improvements, or general enquiries about AI Pulse.</p>
    </div>
    <div style="background:#f8f9fa;border-radius:8px;padding:20px;border-top:3px solid #41e37a">
      <p style="font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#41e37a;margin-bottom:8px">Media</p>
      <p style="font-weight:700;color:#180d3c;margin-bottom:4px">Press &amp; Partnerships</p>
      <p style="font-size:13px;color:#495057">Press enquiries, advertising, or partnership opportunities.</p>
    </div>
  </div>

  <!-- CONTACT FORM -->
  <div style="background:#fff;border:1px solid #e9ecef;border-radius:10px;padding:32px">
    <h2 style="font-size:18px;font-weight:800;color:#180d3c;margin-bottom:24px">Send us a message</h2>
    <form id="contact-form" onsubmit="submitContact(event)">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
        <div>
          <label style="font-size:12px;font-weight:700;color:#495057;display:block;margin-bottom:6px">Your name</label>
          <input id="cf-name" type="text" placeholder="John Smith" maxlength="100" required style="width:100%;padding:10px 14px;border:1.5px solid #e9ecef;border-radius:6px;font-size:14px;font-family:inherit;color:#212529"/>
        </div>
        <div>
          <label style="font-size:12px;font-weight:700;color:#495057;display:block;margin-bottom:6px">Email address</label>
          <input id="cf-email" type="email" placeholder="you@example.com" required style="width:100%;padding:10px 14px;border:1.5px solid #e9ecef;border-radius:6px;font-size:14px;font-family:inherit;color:#212529"/>
        </div>
      </div>
      <div style="margin-bottom:14px">
        <label style="font-size:12px;font-weight:700;color:#495057;display:block;margin-bottom:6px">Subject</label>
        <select id="cf-subject" style="width:100%;padding:10px 14px;border:1.5px solid #e9ecef;border-radius:6px;font-size:14px;font-family:inherit;color:#212529;background:#fff">
          <option value="feedback">Feedback or suggestion</option>
          <option value="correction">Content correction</option>
          <option value="press">Press / media enquiry</option>
          <option value="partnership">Partnership or advertising</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div style="margin-bottom:20px">
        <label style="font-size:12px;font-weight:700;color:#495057;display:block;margin-bottom:6px">Message</label>
        <textarea id="cf-message" placeholder="Tell us what's on your mind..." required maxlength="2000" style="width:100%;padding:10px 14px;border:1.5px solid #e9ecef;border-radius:6px;font-size:14px;font-family:inherit;color:#212529;height:140px;resize:vertical"></textarea>
      </div>
      <button type="submit" style="background:#180d3c;color:#fff;border:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit;width:100%">Send message</button>
      <div id="cf-success" style="display:none;margin-top:16px;background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:14px 18px;font-size:14px;color:#166534;font-weight:600">&#10003; Thank you! We received your message and will reply within 2 business days.</div>
      <div id="cf-error" style="display:none;margin-top:16px;background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;padding:14px 18px;font-size:14px;color:#991b1b"></div>
    </form>
  </div>

  <p style="text-align:center;font-size:13px;color:#868e96;margin-top:28px">Or email us directly: <a href="mailto:contact@aipulse.info" style="color:#28c45e;font-weight:600">contact@aipulse.info</a></p>
</div>

<script>
function submitContact(e){
  e.preventDefault();
  const name = document.getElementById('cf-name').value.trim();
  const email = document.getElementById('cf-email').value.trim();
  const subject = document.getElementById('cf-subject').value;
  const message = document.getElementById('cf-message').value.trim();
  if(!name||!email||!message){return;}
  // Show success (in a real setup this would POST to a backend/formspree)
  document.getElementById('cf-success').style.display='block';
  document.getElementById('cf-error').style.display='none';
  document.getElementById('cf-name').value='';
  document.getElementById('cf-email').value='';
  document.getElementById('cf-message').value='';
  // Track in GA
  if(typeof gtag !== 'undefined'){gtag('event','contact_form_submit',{event_category:'engagement',event_label:subject});}
}
</script>