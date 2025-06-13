---
layout: default
title: Welcome to the AI Discovery Blog
---

Stay updated with the latest news, tools, and research in the world of Artificial Intelligence.

<ul>
  {% for post in site.posts %}
    <li>
      <strong>{{ post.date | date: "%b %d, %Y" }}</strong><br>
      <a href="{{ post.url }}">{{ post.title }}</a>
    </li>
  {% endfor %}
</ul>
