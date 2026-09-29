let current=0;let answers={};let remaining=window.REMAINING;const questions=[...document.querySelectorAll(".question")];

if(window.CHECKPOINT && Object.keys(window.CHECKPOINT).length){answers=window.CHECKPOINT;restoreAnswers();}
show();

function show(){questions.forEach((q,i)=>q.classList.toggle("active",i===current));document.querySelectorAll(".qbtn").forEach((b,i)=>b.classList.toggle("active",i===current));}
function restoreAnswers(){Object.entries(answers).forEach(([qid,val])=>{let el=document.querySelector(`input[name="q${qid}"][value="${val}"]`);if(el)el.checked=true;});}
function collect(){questions.forEach(q=>{let id=q.dataset.qid;let el=document.querySelector(`input[name="q${id}"]:checked`);if(el)answers[id]=Number(el.value);});}
function save(){collect();fetch("/api/checkpoint",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({exam_id:window.EXAM_ID,current_question:current,answers,remaining_time:remaining})}).then(()=>document.getElementById("save").textContent="✓ Checkpoint saved");}
function buttons(){let d=document.getElementById("qbuttons");for(let i=0;i<questions.length;i++){let b=document.createElement("button");b.className="qbtn";b.textContent=i+1;b.onclick=()=>{collect();current=i;show()};d.appendChild(b)}}
buttons();show();
document.getElementById("next").onclick=()=>{collect();if(current<questions.length-1){current++;show()}save()};
document.getElementById("prev").onclick=()=>{collect();if(current>0){current--;show()}save()};
document.getElementById("examForm").onsubmit=()=>{collect();document.getElementById("answers").value=JSON.stringify(answers)};
setInterval(()=>{if(remaining>0){remaining--;let m=Math.floor(remaining/60),s=remaining%60;document.getElementById("timer").textContent=String(m).padStart(2,"0")+":"+String(s).padStart(2,"0")}else document.getElementById("examForm").submit()},1000);
setInterval(save,30000);
document.getElementById("failure").onclick=()=>{collect();fetch("/api/failure",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({exam_id:EXAM_ID,failure_type:"Simulated system/network failure"})}).then(r=>r.json()).then(d=>{document.getElementById("popup").style.display="flex";if(d.ok){answers=d.answers;current=d.current_question;remaining=d.remaining_time}})};
document.getElementById("rollback").onclick=()=>{restoreAnswers();document.getElementById("popup").style.display="none";show();document.getElementById("save").textContent="✓ Last valid checkpoint restored"};
