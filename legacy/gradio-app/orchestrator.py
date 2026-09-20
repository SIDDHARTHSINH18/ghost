import json
import os

import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoTokenizer


class ModelOrchestrator:
    """
    Load local Hugging Face causal language models
    and route chat requests to the selected model.
    """

    def __init__(self, config_path="models.json"):

        self.config_path = config_path

        # Load models.json.
        self.config = self._load_config(config_path)

        # Cache loaded models so they are not loaded repeatedly.
        self.loaded_models = {}

        # Create a convenient name -> configuration mapping.
        self.models_by_name = {
            model["name"]: model
            for model in self.config["models"]
        }

        # Determine default model.
        self.default_model = self.config.get("default_model")

        if self.default_model not in self.models_by_name:
            self.default_model = next(
                iter(self.models_by_name)
            )

        # Detect available hardware.
        self.device = torch.device(
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        # FP16 is appropriate for CUDA.
        # CPU uses FP32 for compatibility.
        self.dtype = (
            torch.float16
            if self.device.type == "cuda"
            else torch.float32
        )

        print("=" * 60)
        print("DeepSeek AI Orchestrator")
        print("=" * 60)
        print(f"Device : {self.device}")
        print(f"Dtype  : {self.dtype}")
        print(f"Models : {len(self.models_by_name)}")
        print(f"Default: {self.default_model}")
        print("=" * 60)

    # =========================================================
    # Configuration
    # =========================================================

    @staticmethod
    def _load_config(config_path):

        if not os.path.exists(config_path):
            raise FileNotFoundError(
                "Model configuration not found:\n"
                f"{os.path.abspath(config_path)}"
            )

        with open(
            config_path,
            "r",
            encoding="utf-8",
        ) as file:

            config = json.load(file)

        models = config.get("models")

        if not isinstance(models, list) or not models:
            raise ValueError(
                "models.json must contain a non-empty 'models' list."
            )

        names = set()

        for model in models:

            if not isinstance(model, dict):
                raise ValueError(
                    "Every model entry must be a JSON object."
                )

            for key in ("name", "endpoint"):

                if not model.get(key):
                    raise ValueError(
                        f"Every model must define '{key}'."
                    )

            if model["name"] in names:
                raise ValueError(
                    f"Duplicate model name: {model['name']}"
                )

            names.add(model["name"])

        return config

    # =========================================================
    # Model loading
    # =========================================================

    def _load_model(self, model_name):
        """
        Load and cache the requested Hugging Face model.
        """

        # Return cached model if already loaded.
        if model_name in self.loaded_models:
            return self.loaded_models[model_name]

        model_cfg = self.models_by_name[model_name]

        endpoint = model_cfg["endpoint"]

        print()
        print(f"Loading model: {model_name}")
        print(f"Endpoint     : {endpoint}")
        print(f"Device       : {self.device}")
        print()

        # Some models require remote code.
        trust_remote_code = bool(
            model_cfg.get(
                "trust_remote_code",
                False,
            )
        )

        # -----------------------------------------------------
        # Tokenizer
        # -----------------------------------------------------

        tokenizer = AutoTokenizer.from_pretrained(
            endpoint,
            trust_remote_code=trust_remote_code,
        )

        # -----------------------------------------------------
        # Model
        # -----------------------------------------------------

        load_kwargs = {
            "torch_dtype": self.dtype,
            "trust_remote_code": trust_remote_code,
        }

        # Automatically distribute model across CUDA devices.
        if self.device.type == "cuda":
            load_kwargs["device_map"] = "auto"

        model = AutoModelForCausalLM.from_pretrained(
            endpoint,
            **load_kwargs,
        )

        # CPU models need to be explicitly moved.
        if self.device.type == "cpu":
            model = model.to(self.device)

        # Inference mode.
        model.eval()

        # -----------------------------------------------------
        # Padding token
        # -----------------------------------------------------

        if tokenizer.pad_token is None:

            if tokenizer.eos_token is None:
                raise RuntimeError(
                    f"Tokenizer for '{model_name}' has neither "
                    "pad_token nor eos_token."
                )

            tokenizer.pad_token = tokenizer.eos_token

        # Cache.
        self.loaded_models[model_name] = (
            model,
            tokenizer,
        )

        print(f"Successfully loaded: {model_name}")

        return model, tokenizer

    # =========================================================
    # Image validation
    # =========================================================

    @staticmethod
    def _validate_image(image_path):

        if not image_path:
            return

        try:

            with Image.open(image_path) as image:
                image.verify()

        except Exception as exc:

            raise ValueError(
                f"Invalid image file: {exc}"
            ) from exc

    # =========================================================
    # Document processing
    # =========================================================

    @staticmethod
    def _process_document(document_path):
        """
        Extract text from TXT or PDF files.
        """

        if not document_path:
            return ""

        extension = os.path.splitext(
            document_path
        )[1].lower()

        # -----------------------------------------------------
        # TXT
        # -----------------------------------------------------

        if extension == ".txt":

            with open(
                document_path,
                "r",
                encoding="utf-8",
                errors="replace",
            ) as file:

                text = file.read()

            return text[:12000]

        # -----------------------------------------------------
        # PDF
        # -----------------------------------------------------

        if extension == ".pdf":

            try:

                import pdfplumber

            except ImportError as exc:

                raise RuntimeError(
                    "PDF support requires pdfplumber.\n"
                    "Run:\n"
                    "pip install -r requirements.txt"
                ) from exc

            pages = []

            with pdfplumber.open(
                document_path
            ) as pdf:

                for page in pdf.pages:

                    text = page.extract_text()

                    if text:
                        pages.append(text)

            full_text = "\n\n".join(pages)

            return full_text[:12000]

        raise ValueError(
            "Unsupported document type. "
            "Please upload a PDF or TXT file."
        )

    # =========================================================
    # History conversion
    # =========================================================

    @staticmethod
    def _history_to_messages(history):
        """
        Convert Gradio chat history into standard
        Hugging Face message dictionaries.
        """

        messages = []

        for item in history or []:

            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in {
                "user",
                "assistant",
                "system",
            }:
                continue

            if not isinstance(content, str):
                continue

            content = content.strip()

            if not content:
                continue

            messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return messages

    # =========================================================
    # Build messages
    # =========================================================

    def _build_messages(
        self,
        user_input,
        history=None,
        document_text="",
    ):
        """
        Build the conversation sent to the model.
        """

        messages = []

        # System prompt.
        system_prompt = self.config.get(
            "system_prompt",
            (
                "You are a helpful AI assistant. "
                "Answer accurately and clearly."
            ),
        )

        if system_prompt.strip():

            messages.append(
                {
                    "role": "system",
                    "content": system_prompt.strip(),
                }
            )

        # Previous conversation.
        messages.extend(
            self._history_to_messages(history)
        )

        # Document context.
        if document_text:

            messages.append(
                {
                    "role": "system",
                    "content": (
                        "The following document was provided "
                        "by the user. Use it as context when "
                        "answering their request.\n\n"
                        f"{document_text}"
                    ),
                }
            )

        # Current user message.
        messages.append(
            {
                "role": "user",
                "content": (
                    user_input.strip()
                    if user_input
                    else "[No text message]"
                ),
            }
        )

        return messages

    # =========================================================
    # Fallback prompt
    # =========================================================

    @staticmethod
    def _build_fallback_prompt(messages):
        """
        Fallback prompt for tokenizers that don't have
        a usable chat template.
        """

        prompt_parts = []

        for message in messages:

            role = message["role"].capitalize()

            prompt_parts.append(
                f"{role}: {message['content']}"
            )

        prompt_parts.append("Assistant:")

        return "\n\n".join(prompt_parts)

    # =========================================================
    # Prepare tokenizer inputs
    # =========================================================

    def _prepare_inputs(
        self,
        tokenizer,
        messages,
        max_input_tokens,
    ):
        """
        Use the tokenizer's native chat template
        whenever possible.
        """

        if hasattr(
            tokenizer,
            "apply_chat_template",
        ):

            try:

                prompt = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )

            except (
                ValueError,
                TypeError,
                AttributeError,
            ):

                prompt = self._build_fallback_prompt(
                    messages
                )

        else:

            prompt = self._build_fallback_prompt(
                messages
            )

        return tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_input_tokens,
        )

    # =========================================================
    # Main request router
    # =========================================================

    def route_request(
        self,
        user_input,
        history=None,
        image=None,
        document=None,
        model_name=None,
    ):
        """
        Route a request to the selected local model.
        """

        # -----------------------------------------------------
        # Select model
        # -----------------------------------------------------

        model_name = (
            model_name
            or self.default_model
        )

        if model_name not in self.models_by_name:

            model_name = self.default_model

        model_cfg = self.models_by_name[
            model_name
        ]

        # -----------------------------------------------------
        # Detect attachments
        # -----------------------------------------------------

        has_image = image is not None
        has_document = document is not None

        # -----------------------------------------------------
        # Image handling
        # -----------------------------------------------------

        # IMPORTANT:
        # The current configured models are text-only causal
        # language models. Base64 image data cannot magically
        # give them vision capability.
        #
        # Therefore, don't pretend the model analyzed the image.

        if has_image:

            self._validate_image(image)

            response = (
                "🖼️ Image received.\n\n"
                "The models currently configured in "
                "`models.json` are text-only language models, "
                "so they cannot actually analyze images.\n\n"
                "Please use a vision-capable model if you want "
                "image understanding."
            )

            return {
                "response": response,
                "model_used": model_name,
                "model_endpoint": model_cfg[
                    "endpoint"
                ],
                "has_image": True,
                "has_document": has_document,
            }

        # -----------------------------------------------------
        # Document handling
        # -----------------------------------------------------

        document_text = ""

        if has_document:

            document_text = (
                self._process_document(
                    document
                )
            )

        # -----------------------------------------------------
        # Load model
        # -----------------------------------------------------

        model, tokenizer = self._load_model(
            model_name
        )

        # -----------------------------------------------------
        # Determine input context size
        # -----------------------------------------------------

        configured_context = int(
            model_cfg.get(
                "context_length",
                4096,
            )
        )

        tokenizer_limit = (
            tokenizer.model_max_length
        )

        if (
            not isinstance(
                tokenizer_limit,
                int,
            )
            or tokenizer_limit <= 0
            or tokenizer_limit >= 1_000_000
        ):

            max_input_tokens = (
                configured_context
            )

        else:

            max_input_tokens = min(
                configured_context,
                tokenizer_limit,
            )

        # -----------------------------------------------------
        # Build conversation
        # -----------------------------------------------------

        messages = self._build_messages(
            user_input=user_input,
            history=history,
            document_text=document_text,
        )

        # -----------------------------------------------------
        # Tokenize
        # -----------------------------------------------------

        inputs = self._prepare_inputs(
            tokenizer=tokenizer,
            messages=messages,
            max_input_tokens=max_input_tokens,
        )

        # Find the actual input device.
        input_device = next(
            model.parameters()
        ).device

        inputs = {
            key: value.to(input_device)
            for key, value in inputs.items()
        }

        # -----------------------------------------------------
        # Generation configuration
        # -----------------------------------------------------

        max_new_tokens = int(
            model_cfg.get(
                "max_new_tokens",
                512,
            )
        )

        # Protect against accidentally huge generation.
        max_new_tokens = max(
            1,
            min(
                max_new_tokens,
                2048,
            ),
        )

        temperature = float(
            model_cfg.get(
                "temperature",
                0.7,
            )
        )

        top_p = float(
            model_cfg.get(
                "top_p",
                0.95,
            )
        )

        repetition_penalty = float(
            model_cfg.get(
                "repetition_penalty",
                1.1,
            )
        )

        generation_kwargs = {
            "max_new_tokens": max_new_tokens,
            "repetition_penalty": repetition_penalty,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
            "do_sample": True,
            "temperature": max(
                0.01,
                temperature,
            ),
            "top_p": min(
                max(top_p, 0.01),
                1.0,
            ),
        }

        # -----------------------------------------------------
        # Generate
        # -----------------------------------------------------

        with torch.inference_mode():

            outputs = model.generate(
                **inputs,
                **generation_kwargs,
            )

        # -----------------------------------------------------
        # Decode ONLY newly generated tokens
        # -----------------------------------------------------

        input_length = (
            inputs["input_ids"].shape[1]
        )

        generated_tokens = (
            outputs[0][input_length:]
        )

        response = tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()

        # -----------------------------------------------------
        # Empty-response protection
        # -----------------------------------------------------

        if not response:

            response = (
                "I couldn't generate a response. "
                "Please try again."
            )

        # -----------------------------------------------------
        # Return result
        # -----------------------------------------------------

        return {
            "response": response,
            "model_used": model_name,
            "model_endpoint": model_cfg[
                "endpoint"
            ],
            "has_image": False,
            "has_document": has_document,
        }