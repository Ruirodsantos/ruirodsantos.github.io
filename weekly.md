---
layout: default
title: "This Week in AI — Weekly Digest"
description: "Your weekly roundup of the most important AI stories. Curated every Sunday from AI Pulse."
permalink: /weekly/
---
<div class="page-wrap" style="max-width:860px;margin:0 auto;padding:32px 20px">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
    <span style="font-size:28px">📰</span>
    <h1 style="font-size:28px;font-weight:800;color:var(--navy);margin:0">This Week in AI</h1>
  </div>
  <p style="color:#888;margin-bottom:32px;font-size:15px">The most important AI stories from the past 7 days — explained simply.</p>

  {% assign cutoff = 'now' | date: '%s' | minus: 604800 %}
  {% assign week_posts = site.posts | where_exp: "p", "p.date.to_i > cutoff" %}
  {% if week_posts.size == 0 %}{% assign week_posts = site.posts | limit: 8 %}{% endif %}

  {% for post in week_posts limit:10 %}
  <div style="display:grid;grid-template-columns:120px 1fr;gap:16px;padding:20px 0;border-bottom:1px solid #f0f0f0;align-items:start">
    <a href="{{ post.url | relative_url }}">
      <div style="width:120px;height:80px;border-radius:8px;background-image:url('{{ post.image }}');background-size:cover;background-position:center;background-color:#eee"></div>
    </a>
    <div>
      <p style="font-size:11px;font-weight:700;color:var(--green,#2d7a4f);text-transform:uppercase;letter-spacing:.06em;margin:0 0 6px">{{ post.categories | first | upcase }}</p>
      <a href="{{ post.url | relative_url }}" style="text-decoration:none">
        <h2 style="font-size:17px;font-weight:700;color:var(--navy);line-height:1.3;margin:0 0 8px">{{ post.title }}</h2>
      </a>
      <p style="font-size:13px;color:#666;line-height:1.6;margin:0 0 8px">{{ post.excerpt | strip_html | truncate: 120 }}</p>
      <span style="font-size:11px;color:#aaa">{{ post.date | date: "%B %d, %Y" }}</span>
    </div>
  </div>
  {% endfor %}

  <div style="margin-top:40px;background:linear-gradient(135deg,#180d3c,#2d7a4f);border-radius:12px;padding:28px;text-align:center">
    <p style="font-size:13px;font-weight:700;color:#86efac;letter-spacing:.08em;text-transform:uppercase;margin:0 0 8px">Get this in your inbox</p>
    <h2 style="font-size:22px;font-weight:800;color:#fff;margin:0 0 12px">Never miss a week</h2>
    <p style="font-size:14px;color:rgba(255,255,255,.75);margin:0 0 20px">Join readers who get the weekly AI digest every Sunday morning.</p>
    <form style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap" onsubmit="return false">
      <input type="email" placeholder="your@email.com" style="padding:10px 18px;border-radius:8px;border:none;font-size:14px;width:240px"/>
      <button style="padding:10px 24px;background:#28c45e;color:#fff;font-weight:700;border:none;border-radius:8px;cursor:pointer;font-size:14px">Subscribe free</button>
    </form>
  </div>
</div>
