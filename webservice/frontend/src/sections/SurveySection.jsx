import React, { useEffect, useState } from "react";
import { surveyQuestions, submitSurvey, latestSurvey } from "../api.js";

export default function SurveySection() {
  const [latest, setLatest] = useState(null);
  const [questions, setQuestions] = useState(null);
  const [answers, setAnswers] = useState({});
  const [error, setError] = useState("");

  useEffect(() => { latestSurvey().then(setLatest).catch(() => {}); }, []);

  async function start() {
    setError("");
    const q = await surveyQuestions();
    setQuestions(q.questions);
    setAnswers(Object.fromEntries(q.questions.map((x) => [x.id, 0])));
  }

  async function submit() {
    try {
      setLatest(await submitSurvey(answers));
      setQuestions(null);
    } catch (e) { setError(e.message); }
  }

  return (
    <section style={{ marginTop: 24 }}>
      <h2>낙상 위험 자가진단</h2>
      {latest && <p>최근 등급: <b>{latest.risk_level}</b> (점수 {latest.score})</p>}
      {!questions && <button onClick={start}>설문 {latest ? "다시 " : ""}하기</button>}
      {questions && (
        <div>
          {questions.map((q) => (
            <div key={q.id} style={{ marginBottom: 8 }}>
              <div>{q.text}</div>
              {q.options.map((o, i) => (
                <label key={i} style={{ marginRight: 12 }}>
                  <input type="radio" name={q.id} checked={answers[q.id] === i}
                         onChange={() => setAnswers({ ...answers, [q.id]: i })} />
                  {o.label}
                </label>
              ))}
            </div>
          ))}
          <button onClick={submit}>제출</button>
          {error && <p style={{ color: "crimson" }}>{error}</p>}
        </div>
      )}
    </section>
  );
}
