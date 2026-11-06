# Setting up Azure OpenAI for handwriting (the `vlm` engine)

Readable sends handwritten pages (and pages Azure OCR is unsure about) to a
vision-capable GPT model on Azure OpenAI. This takes about 15 minutes.

## 1. Create the resource

1. In the Azure portal, search for **Azure OpenAI** and click **Create**.
2. **Basics**
   - Subscription and resource group: the same ones as your existing Computer Vision and Speech resources.
   - Region: **Sweden Central** is usually the EU region with the widest model choice.
     If the model you want is missing in step 2, recreate the resource in another EU region.
   - Name: e.g. `readable-openai` (it becomes part of the endpoint URL).
   - Pricing tier: **Standard S0**.
3. **Network**: *All networks*. The devices connect from people's home Wi-Fi.
4. **Review + create**, then **Create**. It takes a minute or two.

## 2. Deploy a model

1. Open the new resource and click **Go to Foundry portal** (ai.azure.com).
   If the portal shows a *New Foundry* toggle, either view works; the steps below follow the classic one.
2. **Deployments** → **Deploy model** → **Deploy base model**.
3. Pick **gpt-4.1-mini** to start (reads images, low cost). Click **Confirm**.
4. In the deployment dialog:
   - **Deployment name**: `readable-ocr`. This name goes into `config.yaml`.
   - **Deployment type**: choose **Data Zone Standard** with the **EU** zone if it is offered:
     prompts are then processed inside the EU, which matters for prescriptions and medical letters.
     Otherwise use **Global Standard**.
   - Leave the content filter on default. 10K tokens per minute is plenty for testing.
5. **Deploy**.

Other models that work: `gpt-4.1` (more accurate, more expensive), `gpt-4o`,
`gpt-5-mini`. The code handles the GPT-5 family's different parameters.

## 3. Copy the endpoint and key

In the Azure portal, open the resource → **Resource Management** → **Keys and Endpoint**:

- **Endpoint**: `https://readable-openai.openai.azure.com/`
- **KEY 1**: copy it. Treat it like a password and never commit it to git.

## 4. Configure the device

`config.yaml`:

```yaml
vlm:
  enabled: true
  provider: "azure_openai"
  endpoint: "https://readable-openai.openai.azure.com"
  deployment: "readable-ocr"
  api_version: "2024-10-21"
```

`~/.config/readable/readable.env` (see `deploy/readable.env.example`):

```
AZURE_OPENAI_KEY=<KEY 1>
```

## 5. Test

Quick check of the key and deployment, from the device:

```bash
source ~/.config/readable/readable.env
curl "https://readable-openai.openai.azure.com/openai/deployments/readable-ocr/chat/completions?api-version=2024-10-21" \
  -H "api-key: $AZURE_OPENAI_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Πες γεια"}],"max_tokens":20}'
```

A JSON reply with a Greek greeting means it works. A 401 is a wrong key; a 404 is a wrong endpoint or deployment name.

Then a real page: photograph a handwritten Greek note and run

```bash
python3 tools/debug_pipeline.py note.jpg
```

`Source: vlm_azure_openai` and the right text means the full chain works.

## 6. Choose the model with real numbers

Put 15 to 20 photos of Greek handwriting with their `.txt` transcriptions in
`bench/greek_handwriting/` and run `python3 tools/benchmark.py bench/`.
Deploy `gpt-4.1` as a second deployment, switch `deployment:` in `config.yaml`, and run
it again. Pick the cheaper model if the accuracy difference is small.

## 7. Cost control

You pay per token: each handwritten scan sends one image (resized to 1600 px)
and gets back the text. Set a monthly budget alert in **Cost Management** →
**Budgets** on the resource group so a bug can't run up a bill.
Printed pages never reach this model unless Azure OCR is unsure.
