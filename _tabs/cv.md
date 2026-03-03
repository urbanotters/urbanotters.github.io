---
title: CV
icon: fas fa-file-alt
order: 1
---

<div class="lang-switch">
  <span class="lang-active" id="lang-en" onclick="switchCV('en')">EN</span>
  <span class="lang-inactive" id="lang-kr" onclick="switchCV('kr')">KR</span>
</div>

<div id="cv-en">
  <div class="cv-embed">
    <iframe src="/assets/docs/CV_Suhyeon_Shin_CBP.pdf" title="CV (EN)"></iframe>
  </div>
  <p class="text-center mt-3">
    <a href="/assets/docs/CV_Suhyeon_Shin_CBP.pdf" class="btn btn-outline-primary btn-sm" download>
      <i class="fas fa-download me-1"></i>Download PDF
    </a>
  </p>
</div>

<div id="cv-kr" style="display:none">
  <div class="cv-embed">
    <iframe src="/assets/docs/resume_202411.pdf" title="CV (KR)"></iframe>
  </div>
  <p class="text-center mt-3">
    <a href="/assets/docs/resume_202411.pdf" class="btn btn-outline-primary btn-sm" download>
      <i class="fas fa-download me-1"></i>Download PDF
    </a>
  </p>
</div>

<script>
function switchCV(lang) {
  var enDiv = document.getElementById('cv-en');
  var krDiv = document.getElementById('cv-kr');
  var enBtn = document.getElementById('lang-en');
  var krBtn = document.getElementById('lang-kr');
  if (lang === 'kr') {
    enDiv.style.display = 'none';
    krDiv.style.display = 'block';
    enBtn.className = 'lang-inactive';
    krBtn.className = 'lang-active';
  } else {
    enDiv.style.display = 'block';
    krDiv.style.display = 'none';
    enBtn.className = 'lang-active';
    krBtn.className = 'lang-inactive';
  }
}
</script>
