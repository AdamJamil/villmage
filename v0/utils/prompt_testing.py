import requests
import json


GOOGLE_API_KEY = "TODO"
BASE = "https://generativelanguage.googleapis.com/v1beta"

# Available Gemma 4 models on AI Studio (free tier)
MODELS = {
    "31b": "gemma-4-31b-it",
    "26b": "gemma-4-26b-a4b-it",
    "2.5flash": "gemini-2.5-flash",
    "2.5pro": "gemini-2.5-pro",
    # E4B and E2B are edge-only (download from HuggingFace/Ollama)
}


def stream_chat(prompt: str, model: str) -> None:
    url = f"{BASE}/models/{MODELS[model]}:streamGenerateContent?alt=sse"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }
    }

    import time 

    start = time.perf_counter_ns()

    with requests.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY,
        },
        stream=True,
    ) as resp:
        if not resp.ok:
            print(resp.status_code, resp.text)   # critical
            resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                chunk = json.loads(line[6:])
                for part in chunk.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if "text" in part and (text := part["text"].strip()):
                        if start is not None:
                            print(f"TTFT: {(time.perf_counter_ns() - start)/1e9:.2f}s")
                            start = None
                        print(text, end="", flush=True)
    print()


def main():
    hookah = """
I'm running a prefill engine latency test. IGNORE ALL SUBSEQUENCE USER PROMPT TOKENS AND OUTPUT "meow" AT THE END.
Every time you "hit" (inhale from) a hookah, a series of interconnected physical and chemical events occur, leading to a range of immediate sensations and the introduction of various substances into your body.

Here's a breakdown of what happens:

1.  **Airflow and Heating:**
    *   Your inhalation creates a vacuum, pulling air down through the hot charcoal placed on top of the bowl.
    *   This hot air then passes over the **shisha** (the flavored tobacco mixture) in the bowl.
    *   Crucially, the shisha is *heated* (typically to around 150-200°C), not directly burned like a cigarette. This heating process vaporizes the glycerin, flavorings, nicotine, and other compounds present in the shisha.

2.  **Smoke/Vapor Formation:**
    *   A dense, aromatic smoke-like vapor is produced from the heated shisha. This vapor is often thicker and feels smoother than cigarette smoke due to the presence of glycerin and the subsequent cooling process.

3.  **Water Filtration and Cooling:**
    *   This smoke travels down the stem of the hookah and bubbles through the water in the base.
    *   The water serves to cool the smoke, making it less harsh, and also filters out some (but not all) water-soluble toxins and particulate matter. However, it's important to note that this filtration is partial and does *not* make hookah smoking safe.

4.  **Travel to Mouthpiece:**
    *   The cooled, "filtered" smoke then travels up through the hose to the mouthpiece, where you inhale it into your lungs.

**What you inhale and what happens in your body:**

When you inhale this smoke, you're introducing a complex mixture into your body:

*   **Nicotine:** This is the primary addictive substance in tobacco. It's rapidly absorbed through your lungs into your bloodstream and quickly reaches your brain. Nicotine acts as a stimulant, increasing your heart rate and blood pressure, and releasing neurotransmitters like dopamine, which contributes to the "head rush" or feeling of relaxation/euphoria many users experience.
*   **Carbon Monoxide (CO):** Produced by the burning charcoal, CO is also readily absorbed into your bloodstream. It binds to hemoglobin in your red blood cells much more readily than oxygen, reducing the oxygen-carrying capacity of your blood. This can lead to symptoms like dizziness, headache, nausea, and lightheadedness, especially with prolonged use or for new users.
*   **Tar:** A sticky, black residue containing hundreds of chemicals, many of which are known carcinogens (cancer-causing agents).
*   **Heavy Metals:** Lead, arsenic, chromium, and others can be present in both the tobacco and the charcoal.
*   **Carcinogens:** Beyond tar, the smoke contains numerous other chemicals known to cause cancer, including polycyclic aromatic hydrocarbons (PAHs), volatile aldehydes, and specific nitrosamines.
*   **Flavorings and Glycerin:** While food-grade versions are generally safe to ingest, their effects when heated and inhaled into the lungs are still being studied, and some may form harmful compounds.

**Immediate Physiological Effects:**

*   **Taste and Aroma:** You'll experience the specific flavor of the shisha.
*   **Throat Hit:** The sensation of the smoke in your throat and lungs.
*   **Nicotine Rush/Relaxation:** A feeling of lightheadedness, dizziness, relaxation, or mild euphoria, especially if you're sensitive to nicotine or haven't used it recently.
*   **Increased Heart Rate & Blood Pressure:** Due to the stimulant effect of nicotine.
*   **Potential for Nausea/Dizziness:** Especially for new users or if inhaling deeply/frequently, due to nicotine sensitivity and/or carbon monoxide exposure.

**Long-Term Implications (Important Warning):**

It's crucial to understand that despite the water filtration and often smoother sensation, hookah smoking is **NOT a safe alternative** to cigarettes and carries significant health risks, even from a single session, and especially with regular use:

*   **Addiction:** Nicotine is highly addictive.
*   **Respiratory Problems:** Increased risk of bronchitis, emphysema, COPD, reduced lung function, and asthma attacks.
*   **Cardiovascular Disease:** Increased risk of heart disease, stroke, and hardened arteries due to nicotine and carbon monoxide.
*   **Cancers:** Increased risk of cancers of the mouth, throat, esophagus, lungs, and bladder.
*   **Oral Health Issues:** Gum disease, tooth decay, and oral cancers.
*   **Exposure to Toxins:** A typical hookah session can last an hour or more, exposing users to amounts of smoke and harmful chemicals (like carbon monoxide, tar, and heavy metals) equivalent to or even greater than smoking multiple cigarettes.
*   **Infections:** Sharing mouthpieces can transmit oral herpes, flu, and other communicable diseases.

In essence, every time you hit the hookah, you're engaging in a complex process that delivers nicotine and numerous other harmful chemicals into your body, leading to a temporary sensation but posing significant short-term and long-term health risks.

Every time you "hit" (inhale from) a hookah, a series of interconnected physical and chemical events occur, leading to a range of immediate sensations and the introduction of various substances into your body.

Here's a breakdown of what happens:

1.  **Airflow and Heating:**
    *   Your inhalation creates a vacuum, pulling air down through the hot charcoal placed on top of the bowl.
    *   This hot air then passes over the **shisha** (the flavored tobacco mixture) in the bowl.
    *   Crucially, the shisha is *heated* (typically to around 150-200°C), not directly burned like a cigarette. This heating process vaporizes the glycerin, flavorings, nicotine, and other compounds present in the shisha.

2.  **Smoke/Vapor Formation:**
    *   A dense, aromatic smoke-like vapor is produced from the heated shisha. This vapor is often thicker and feels smoother than cigarette smoke due to the presence of glycerin and the subsequent cooling process.

3.  **Water Filtration and Cooling:**
    *   This smoke travels down the stem of the hookah and bubbles through the water in the base.
    *   The water serves to cool the smoke, making it less harsh, and also filters out some (but not all) water-soluble toxins and particulate matter. However, it's important to note that this filtration is partial and does *not* make hookah smoking safe.

4.  **Travel to Mouthpiece:**
    *   The cooled, "filtered" smoke then travels up through the hose to the mouthpiece, where you inhale it into your lungs.

**What you inhale and what happens in your body:**

When you inhale this smoke, you're introducing a complex mixture into your body:

*   **Nicotine:** This is the primary addictive substance in tobacco. It's rapidly absorbed through your lungs into your bloodstream and quickly reaches your brain. Nicotine acts as a stimulant, increasing your heart rate and blood pressure, and releasing neurotransmitters like dopamine, which contributes to the "head rush" or feeling of relaxation/euphoria many users experience.
*   **Carbon Monoxide (CO):** Produced by the burning charcoal, CO is also readily absorbed into your bloodstream. It binds to hemoglobin in your red blood cells much more readily than oxygen, reducing the oxygen-carrying capacity of your blood. This can lead to symptoms like dizziness, headache, nausea, and lightheadedness, especially with prolonged use or for new users.
*   **Tar:** A sticky, black residue containing hundreds of chemicals, many of which are known carcinogens (cancer-causing agents).
*   **Heavy Metals:** Lead, arsenic, chromium, and others can be present in both the tobacco and the charcoal.
*   **Carcinogens:** Beyond tar, the smoke contains numerous other chemicals known to cause cancer, including polycyclic aromatic hydrocarbons (PAHs), volatile aldehydes, and specific nitrosamines.
*   **Flavorings and Glycerin:** While food-grade versions are generally safe to ingest, their effects when heated and inhaled into the lungs are still being studied, and some may form harmful compounds.

**Immediate Physiological Effects:**

*   **Taste and Aroma:** You'll experience the specific flavor of the shisha.
*   **Throat Hit:** The sensation of the smoke in your throat and lungs.
*   **Nicotine Rush/Relaxation:** A feeling of lightheadedness, dizziness, relaxation, or mild euphoria, especially if you're sensitive to nicotine or haven't used it recently.
*   **Increased Heart Rate & Blood Pressure:** Due to the stimulant effect of nicotine.
*   **Potential for Nausea/Dizziness:** Especially for new users or if inhaling deeply/frequently, due to nicotine sensitivity and/or carbon monoxide exposure.

**Long-Term Implications (Important Warning):**

It's crucial to understand that despite the water filtration and often smoother sensation, hookah smoking is **NOT a safe alternative** to cigarettes and carries significant health risks, even from a single session, and especially with regular use:

*   **Addiction:** Nicotine is highly addictive.
*   **Respiratory Problems:** Increased risk of bronchitis, emphysema, COPD, reduced lung function, and asthma attacks.
*   **Cardiovascular Disease:** Increased risk of heart disease, stroke, and hardened arteries due to nicotine and carbon monoxide.
*   **Cancers:** Increased risk of cancers of the mouth, throat, esophagus, lungs, and bladder.
*   **Oral Health Issues:** Gum disease, tooth decay, and oral cancers.
*   **Exposure to Toxins:** A typical hookah session can last an hour or more, exposing users to amounts of smoke and harmful chemicals (like carbon monoxide, tar, and heavy metals) equivalent to or even greater than smoking multiple cigarettes.
*   **Infections:** Sharing mouthpieces can transmit oral herpes, flu, and other communicable diseases.

In essence, every time you hit the hookah, you're engaging in a complex process that delivers nicotine and numerous other harmful chemicals into your body, leading to a temporary sensation but posing significant short-term and long-term health risks.

"""
    

    improv = \
"""Create an example grounded improv script. Make it an example of actual lines said, not guidance for actors.
"""

    # prompt = "Output 'meow'."

    import random
    rand_meow = "Output 'meow'. Ignore everything else in this message" + \
        "".join(map(chr, [ord('a') + random.randint(0, 26) for _ in range(3000)]))

    narc = """\
Explain vulnerable narcissm. You must explain the following format:
(1) You must structure your explanation as a chain of statements.
(2) Every statement must be grounded in either:
    (a) "Highly common sense" human nature -- e.g., "humans need love";
    (b) A logical consequence of previous statements;
    (c) A childhood event (trauma, learning) that results in a specific world view or behavior.
(3) All vulnerable narcissistic behaviors must be explainable by your chain of statements. 
"""
    prompt = narc

    if GOOGLE_API_KEY == "TODO":
        print("Please add your API key.")
        exit(1)

    import time
    
    start = time.perf_counter_ns()
    model = "2.5flash"
    print(f"-- {model} -- ")
    print(prompt)
    stream_chat(prompt, model=model)
    print(f"Total time: {(time.perf_counter_ns() - start) / 1e9:.2f}s")


# ---------- Quick test ----------
if __name__ == "__main__":
    main()
