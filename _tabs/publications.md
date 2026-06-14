---
title: Publications
icon: fas fa-pen-nib
order: 2
---

{% assign media_pubs = site.data.publications | where: "category", "media" | sort: "date" | reverse %}
{% assign collab_pubs = site.data.publications | where: "category", "collab" | sort: "date" | reverse %}
{% assign talk_pubs = site.data.publications | where: "category", "talk" | sort: "date" | reverse %}

## 언론기고

{% for pub in media_pubs %}
- [{{ pub.title }}]({{ pub.url }}) — {{ pub.outlet }}, {{ pub.date | date: "%Y.%m" }}
{% endfor %}

## 외부협업 (기획 및 데이터분석)

{% for pub in collab_pubs %}
- [{{ pub.title }}]({{ pub.url }}) — {{ pub.outlet }}
{% endfor %}

## 강연 / 미디어

{% for pub in talk_pubs %}
- [{{ pub.title }}]({{ pub.url }})
{% endfor %}
