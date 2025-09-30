
// 여러 파일 업로드 및 중복시 덮어쓰기 확인
document.getElementById('upload').addEventListener('change', function(e) {
  const files = Array.from(e.target.files);
  if (!files.length) return;
  const progressList = document.getElementById('upload-progress-list');
  progressList.innerHTML = '';
  let finished = 0;
  files.forEach((file, idx) => {
    // 파일별 진행률 bar/상태 생성
    const wrapper = document.createElement('div');
    wrapper.className = 'upload-item';
    wrapper.style.marginBottom = '12px';
    wrapper.innerHTML = `
      <div style="font-size:15px;color:#222;margin-bottom:4px;">${file.name}</div>
      <div style="background:#e3eafc;border-radius:6px;height:16px;width:100%;overflow:hidden;">
        <div class="upload-bar" style="background:linear-gradient(90deg,#0366d6,#4f8cff);height:100%;width:0%;transition:width 0.2s;"></div>
      </div>
      <div class="upload-status" style="font-size:13px;color:#0366d6;margin-top:4px;text-align:right;">0%</div>
    `;
    progressList.appendChild(wrapper);
    // 업로드 시작
    function uploadFile(overwrite=false) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('overwrite', overwrite ? '1' : '0');
      const bar = wrapper.querySelector('.upload-bar');
      const status = wrapper.querySelector('.upload-status');
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/upload');
      xhr.upload.onprogress = function(ev) {
        if (ev.lengthComputable) {
          const p = Math.round((ev.loaded / ev.total) * 100);
          bar.style.width = p + '%';
          status.textContent = p + '%';
        }
      };
      xhr.onload = function() {
  let res;
  try { res = JSON.parse(xhr.responseText); } catch {}
  console.log('업로드 응답:', res); // 업로드 결과 전체 콘솔 출력
        if (xhr.status === 200 && res && res.message === 'Azure Storage 업로드 성공') {
          bar.style.width = '100%';
          status.textContent = '업로드 완료!';
          status.style.color = '#1b8c3a';
        } else if (res && res.error && res.error.includes('이미 존재')) {
          bar.style.width = '0%';
          status.textContent = '중복 파일, 업로드 안됨';
          status.style.color = '#d32f2f';
          // 덮어쓰기 여부 확인
          if (confirm(`${file.name} 파일이 이미 존재합니다. 덮어쓰시겠습니까?`)) {
            uploadFile(true);
            return;
          }
        } else {
          status.textContent = '업로드 실패';
          status.style.color = '#d32f2f';
        }
        finished++;
        if (finished === files.length) {
          // 모든 파일 업로드 완료 시
          setTimeout(() => {
            progressList.innerHTML = '<div style="color:#1b8c3a;font-size:16px;text-align:center;">업로드 완료!</div>';
            setTimeout(() => { progressList.innerHTML = ''; }, 1200);
          }, 400);
        }
      };
      xhr.onerror = function() {
        status.textContent = '업로드 오류';
        status.style.color = '#d32f2f';
        finished++;
        if (finished === files.length) {
          setTimeout(() => {
            progressList.innerHTML = '<div style="color:#1b8c3a;font-size:16px;text-align:center;">업로드 완료!</div>';
            setTimeout(() => { progressList.innerHTML = ''; }, 1200);
          }, 400);
        }
      };
      xhr.send(formData);
    }
    uploadFile(false);
  });
});

async function search(){
  const q = document.getElementById('query').value.trim();
  const topk = Number(document.getElementById('topk').value) || 5;
  const resDiv = document.getElementById('results');
  if(!q){
    resDiv.innerHTML = '<div style="padding:18px 0;color:#d32f2f;font-size:16px;text-align:center;">요구사항을 입력해 주세요.</div>';
    return;
  }
  resDiv.innerHTML = '<div style="padding:18px 0;color:#0366d6;font-size:16px;text-align:center;">검색 중...</div>';
  try{
    const r = await fetch(`/search?q=${encodeURIComponent(q)}&top_k=${topk}`);
    let j, rawText;
    try {
      rawText = await r.text();
      j = JSON.parse(rawText);
    } catch (e) {
      resDiv.innerHTML = `<p class="error">서버 오류: ${rawText || r.statusText}</p>`;
      return;
    }
    if(!r.ok){
      resDiv.innerHTML = `<p class="error">오류: ${(j && j.detail) || r.statusText}</p>`;
      return;
    }
    if(!j.결과 || j.결과.length===0){
      resDiv.innerHTML = '<div style="padding:18px 0;color:#888;font-size:16px;text-align:center;">검색 결과가 없습니다.<br>입력한 요구사항에 맞는 문서를 찾지 못했습니다.</div>';
      return;
    }
    resDiv.innerHTML = j.결과.map((it, i)=>`
      <div class="result" data-idx="${i}" style="cursor:pointer;position:relative;">
        <h3 style="display:flex;align-items:center;gap:10px;">
          <span>${i+1}. ${it.문서명}</span>
          <button class="download-btn" data-filename="${it.문서명}" style="font-size:13px;padding:3px 10px;border-radius:5px;border:1px solid #0366d6;background:#f3f8ff;color:#0366d6;cursor:pointer;">다운로드</button>
        </h3>
        <p>유사도: ${it.유사도.toFixed(2)}점</p>
        <p>${it.본문 ? it.본문 : ''}</p>
      </div>
    `).join('');
    // 다운로드 버튼 이벤트 추가
    Array.from(document.querySelectorAll('.download-btn')).forEach(btn => {
      btn.addEventListener('click', async function(e) {
        e.stopPropagation();
        const filename = btn.getAttribute('data-filename');
        if (!confirm(`${filename} 파일을 다운로드 하시겠습니까?`)) return;
        btn.textContent = '다운로드 중...';
        btn.disabled = true;
        try {
          const resp = await fetch(`/download?filename=${encodeURIComponent(filename)}`);
          if (!resp.ok) throw new Error('다운로드 실패');
          const blob = await resp.blob();
          // 파일 저장
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          setTimeout(() => {
            window.URL.revokeObjectURL(url);
            a.remove();
          }, 1000);
          btn.textContent = '다운로드';
        } catch(e) {
          alert('다운로드 오류: ' + e.message);
          btn.textContent = '다운로드';
        }
        btn.disabled = false;
      });
    });
    // 결과 클릭 시 요약/키워드 요청
    Array.from(document.querySelectorAll('.result')).forEach((el, idx) => {
      let summaryVisible = false;
      el.addEventListener('click', async function() {
        // 요약/키워드 박스가 이미 있으면 제거(토글)
        const summaryBox = el.querySelector('.summary-box');
        if (summaryBox) {
          summaryBox.remove();
          summaryVisible = false;
          return;
        }
        if (summaryVisible) return; // 이미 생성된 경우 중복 방지
        // 기존 요약/키워드 박스 모두 제거
        const allSummary = el.querySelectorAll('.summary-box');
        allSummary.forEach(box => box.remove());
        // 요약/키워드 생성 진행 표시
        if (el.querySelector('.summarizing')) return; // 이미 진행 중이면 무시
        el.style.opacity = '0.6';
        el.style.pointerEvents = 'none';
        el.insertAdjacentHTML('beforeend', `<div class="summarizing" style="color:#0366d6;font-size:15px;margin-top:8px;">요약 및 키워드 생성 중...</div>`);
        try {
          const doc = j.결과[idx];
          console.log('요약/키워드 생성 요청 본문:', doc.본문);
          const resp = await fetch('/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: doc.본문, source: doc.문서명, query: document.getElementById('query').value })
          });
          const data = await resp.json();
          el.querySelector('.summarizing').remove();
          el.style.opacity = '1';
          el.style.pointerEvents = '';
          if (data.error) {
            alert('요약/키워드 생성 오류: ' + data.error);
            summaryVisible = false;
            return;
          }
          el.insertAdjacentHTML('beforeend', `
            <div class="summary-box" style="background:#f6f8fa;border-radius:8px;padding:12px;margin-top:10px;">
              <div style="font-weight:600;color:#0366d6;margin-bottom:6px;">키워드</div>
              <div style="color:#222;margin-bottom:10px;">${data.keywords}</div>
              <div style="font-weight:600;color:#0366d6;margin-bottom:6px;">요약</div>
              <div style="color:#222;">${data.summary}</div>
            </div>
          `);
          summaryVisible = true;
        } catch(e) {
          el.querySelector('.summarizing').remove();
          el.style.opacity = '1';
          el.style.pointerEvents = '';
          alert('요약/키워드 생성 오류: ' + e.message);
          summaryVisible = false;
        }
      });
    });
// ...existing code...
  }catch(e){
    resDiv.innerHTML = `<p class="error">예외 발생: ${e.message}</p>`;
  }
}

document.getElementById('search').addEventListener('click', search);
