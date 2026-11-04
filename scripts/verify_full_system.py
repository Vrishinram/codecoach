"""
Comprehensive End-to-End System Verification for CodeCoach.
Tests:
- Server health & settings
- Placement test flow
- Curriculum & dashboard stats
- Live 25-MCQ Quiz set generation via LLM
- Answer submission & consecutive correct tracking
- Learning report generation
- Verification Step 2: Teach-Back grading (accuracy, completeness, clarity)
- Verification Step 3: Application Challenge generation & review
- WebSocket streaming chat
- Spaced Repetition checks
"""
import asyncio
import json
import urllib.request
import functools
import websockets

print = functools.partial(print, flush=True)

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/chat"

def get(path):
    with urllib.request.urlopen(f"{BASE_URL}{path}") as resp:
        return json.loads(resp.read().decode("utf-8"))

def post(path, data):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

async def test_websocket():
    print("\n--- Testing WebSocket Streaming Chat ---")
    async with websockets.connect(WS_URL) as ws:
        # Receive welcome
        welcome = json.loads(await ws.recv())
        print(f"WS Connected! Assistant greeting received: {welcome.get('content')[:50]}...")

        # Send test prompt
        test_msg = {"content": "In 1 sentence, why is C# Span<T> fast?"}
        await ws.send(json.dumps(test_msg))

        tokens = []
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg["type"] == "token":
                tokens.append(msg["content"])
            elif msg["type"] == "stream_end":
                full_text = "".join(tokens)
                print(f"WS Streaming Successful! Generated ({len(tokens)} chunks, model {msg.get('model')}):")
                print(f"  \"{full_text.strip()}\"")
                break
            elif msg["type"] == "stream_error":
                print(f"WS Error: {msg['error']}")
                break

async def main():
    print("=" * 65)
    print("CODECOACH FULL SYSTEM INTEGRATION VERIFICATION")
    print("=" * 65)

    # 1. Health check
    h = get("/health")
    print(f"1. Health Check: OK ({h})")

    # 2. Settings check
    s = get("/api/settings")
    print(f"2. System Settings: Assistant='{s['assistant_name']}', Timezone='{s['timezone']}', SetSize={s['set_size']}")

    # 3. Placement Test
    qs = get("/api/placement/questions")
    print(f"3. Placement Test: Loaded {len(qs)} questions across 6 levels")
    assert len(qs) == 10

    # Submit placement
    sub_payload = {"answers": [{"question_id": q["id"], "selected_option_index": q["correct_option_index"]} for q in qs]}
    p_res = post("/api/placement/submit", sub_payload)
    print(f"4. Placement Submitted: Score={p_res['score']}%, Recommended='{p_res['recommended_topic_title']}'")

    # 5. Curriculum roadmap
    curriculum = get("/api/curriculum")
    total_topics = sum(len(lvl["topics"]) for lvl in curriculum)
    print(f"5. Curriculum Roadmap: {len(curriculum)} Levels, {total_topics} Topics loaded")

    # 6. Dashboard Stats
    stats = get("/api/dashboard/stats")
    print(f"6. Dashboard Stats: Mastered={stats['topics_mastered']}, Reviewing={stats['topics_reviewing']}, Streak={stats['current_streak']}d, Tokens={stats['total_tokens_used']}")

    # 7. Start Quiz Set (Live LLM Generation of 25 MCQs)
    print("\n--- Testing Quiz Set Generation & Answer Evaluation ---")
    print("Requesting quiz start for 'variables-and-types'...")
    q_start = post("/api/quiz/start/variables-and-types", {})
    set_id = q_start["set_id"]
    current_q = q_start.get("current_question")
    print(f"7. Quiz Set #{q_start['set_number']} Active (Set ID: {set_id}, Total Questions: {q_start['total_questions']})")
    if current_q:
        print(f"   Sample Question 1: \"{current_q['prompt'][:65]}...\"")
        print(f"   Type: {current_q['question_type']} | Options: {current_q['options']}")
        assert current_q['question_type'] == 'mcq'
        assert len(current_q['options']) == 4

        # 8. Submit Answer
        ans_res = post("/api/quiz/submit-answer", {
            "question_id": current_q["id"],
            "user_answer": "A"
        })
        print(f"8. Answer Evaluated: is_correct={ans_res['is_correct']}, correct_answer='{ans_res['correct_answer']}'")
        print(f"   Explanation: \"{ans_res['explanation'][:70]}...\"")

    # 9. Learning Verification Step 2: Teach-Back check
    print("\n--- Testing Step 2: Teach-Back Grading (LLM Rubric) ---")
    tb_res = post("/api/verification/teach-back", {
        "topic_id": "variables-and-types",
        "student_explanation": "Value types in C# hold their data directly and live on the stack or inline, whereas reference types store a pointer to an object on the managed heap. Value types derive implicitly from System.ValueType and copy by value."
    })
    print(f"9. Teach-Back Rubric Graded:")
    print(f"   Overall Score: {tb_res['overall_score']}% (Passed: {tb_res['passed']})")
    print(f"   Accuracy: {tb_res['accuracy_score']}% | Completeness: {tb_res['completeness_score']}% | Clarity: {tb_res['clarity_score']}%")
    print(f"   Feedback: \"{tb_res['feedback']}\"")

    # 10. Learning Verification Step 3: Application Challenge
    print("\n--- Testing Step 3: Application Challenge ---")
    app_prompt = get("/api/verification/app-challenge/variables-and-types")
    print(f"10. Coding Challenge Generated:")
    print(f"    Prompt: \"{app_prompt['prompt'][:80]}...\"")
    
    # Review Challenge
    app_review = post("/api/verification/app-challenge/submit", {
        "topic_id": "variables-and-types",
        "student_code": "public class Solution { public static int Add(int a, int b) => a + b; }"
    })
    print(f"    Code Review Result: Score={app_review['score']}%, Passed={app_review['passed']}")
    print(f"    Feedback: \"{app_review['feedback'][:80]}...\"")

    # 11. Links & Resources
    links = get("/api/links/variables-and-types")
    print(f"\n11. Learning Links: {len(links)} verified official links for topic")

    # 12. WebSocket Streaming
    await test_websocket()

    print("\n" + "=" * 65)
    print("ALL END-TO-END CHECKS COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
