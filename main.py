from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import re
import shutil
import sys
import time
import unicodedata
import warnings
from collections import Counter
from pathlib import Path

import easyocr
import numpy as np
import pandas as pd
import pytesseract
from paddleocr import PaddleOCR
from PIL import Image, ImageFilter, ImageOps

from result_report import save_korean_results


warnings.filterwarnings("ignore")
# Windows CPU 환경에서 PaddleOCR / PaddleX 충돌 방지 설정
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "samples"
MANIFEST_PATH = ROOT / "manifest.json"
ANSWER_SHEET_PATH = SAMPLES_DIR / "정답표.csv"
RESULTS_ROOT = ROOT / "결과"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
ENGINES = ["Tesseract", "EasyOCR", "PaddleOCR"]
PHASE_LABELS = {"baseline": "전처리 전", "preprocessed": "전처리 후"}
ENGINE_ORDERS = [
    ["Tesseract", "EasyOCR", "PaddleOCR"],
    ["EasyOCR", "PaddleOCR", "Tesseract"],
    ["PaddleOCR", "Tesseract", "EasyOCR"],
]
PIPELINES = {
    "Tesseract": {
        "name": "denoise_upscale_sharpen",
        "description": "회색조 명암 보정 Median 노이즈 제거 2배 확대 선명화",
    },
    "EasyOCR": {
        "name": "contrast_sharpen",
        "description": "회색조 명암 보정 선명화",
    },
    "PaddleOCR": {
        "name": "contrast_sharpen",
        "description": "회색조 명암 보정 선명화",
    },
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="보고서 기준 Tesseract EasyOCR PaddleOCR 전처리 전후 비교"
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=30,
        help="전처리 전과 후에 각각 적용할 반복 횟수. 기본값은 30입니다.",
    )
    parser.add_argument(
        "--prepare-models",
        action="store_true",
        help="EasyOCR과 PaddleOCR 모델만 미리 내려받고 종료합니다.",
    )
    return parser.parse_args()


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text)).upper()
    return re.sub(r"[^A-Z0-9]", "", normalized)


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_character in enumerate(left, start=1):
        current = [i]
        for j, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def load_answer_sheet() -> dict[str, dict]:
    if not ANSWER_SHEET_PATH.is_file():
        return {}

    table = pd.read_csv(
        ANSWER_SHEET_PATH,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    aliases = {
        "파일명": ["파일명", "filename"],
        "정답": ["정답", "ground_truth"],
        "조건": ["조건", "condition"],
    }
    columns = {}
    for name, candidates in aliases.items():
        columns[name] = next(
            (candidate for candidate in candidates if candidate in table.columns),
            None,
        )
    if not columns["파일명"] or not columns["정답"]:
        raise ValueError(
            "samples/정답표.csv에는 '파일명'과 '정답' 열이 필요합니다."
        )

    lookup = {}
    for _, row in table.iterrows():
        filename = str(row[columns["파일명"]]).strip()
        answer = str(row[columns["정답"]]).strip()
        if not filename or filename.lower() == "nan":
            continue
        if not answer or answer.lower() == "nan":
            raise ValueError(f"정답표에서 정답이 비어 있습니다: {filename}")
        condition = "사용자 샘플"
        if columns["조건"] and row[columns["조건"]]:
            condition = str(row[columns["조건"]]).strip() or condition
        lookup[filename.casefold()] = {
            "ground_truth": answer,
            "condition": condition,
            "answer_source": "정답표",
        }
    return lookup


def infer_from_filename(image_path: Path) -> dict | None:
    parts = [part.strip() for part in image_path.stem.split("__")]
    if len(parts) >= 3:
        answer = parts[0]
        description = parts[1]
        condition = (
            "사용자 샘플"
            if not description or description.isdigit()
            else description.replace("_", " ")
        )
        if answer:
            return {
                "ground_truth": answer,
                "condition": condition,
                "answer_source": "파일명",
            }
    return {
        "ground_truth": None,
        "condition": "사용자 샘플",
        "answer_source": "자동 합의",
    }


def load_manifest() -> tuple[list[dict], bool]:
    if not SAMPLES_DIR.is_dir():
        raise FileNotFoundError(f"samples 폴더를 찾을 수 없습니다: {SAMPLES_DIR}")

    image_paths = sorted(
        path
        for path in SAMPLES_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not image_paths:
        raise FileNotFoundError("samples 폴더에 인식할 이미지가 없습니다.")

    original_manifest = []
    if MANIFEST_PATH.is_file():
        original_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    original_lookup = {
        str(item["filename"]).casefold(): item
        for item in original_manifest
        if "filename" in item
    }
    answer_lookup = load_answer_sheet()
    manifest = []
    unresolved = []
    seen_stems = set()

    for image_path in image_paths:
        key = image_path.name.casefold()
        if key in answer_lookup:
            metadata = answer_lookup[key]
        elif key in original_lookup:
            metadata = {**original_lookup[key], "answer_source": "기본 정답"}
        else:
            metadata = infer_from_filename(image_path)

        if metadata is None:
            unresolved.append(image_path.name)
            continue
        if image_path.stem.casefold() in seen_stems:
            raise ValueError(
                f"확장자만 다른 같은 이름의 이미지가 있습니다: {image_path.stem}"
            )
        seen_stems.add(image_path.stem.casefold())
        manifest.append(
            {
                "stem": image_path.stem,
                "filename": image_path.name,
                "ground_truth": (
                    str(metadata["ground_truth"])
                    if metadata.get("ground_truth") is not None
                    else None
                ),
                "condition": str(metadata.get("condition", "사용자 샘플")),
                "answer_source": str(
                    metadata.get("answer_source", "자동 합의")
                ),
                "scorable": metadata.get("ground_truth") is not None,
            }
        )

    if unresolved:
        preview = ", ".join(unresolved[:5])
        raise ValueError(
            "다음 이미지의 정답을 알 수 없습니다: "
            f"{preview}. 파일명을 '정답__조건__번호.jpg' 형식으로 바꾸거나 "
            "samples/정답표.csv에 파일명과 정답을 적어주세요."
        )

    original_names = {str(item.get("filename", "")).casefold() for item in original_manifest}
    current_names = {path.name.casefold() for path in image_paths}
    is_original_report_set = (
        bool(original_manifest)
        and not answer_lookup
        and current_names == original_names
        and all(item["answer_source"] == "기본 정답" for item in manifest)
    )
    print(f"샘플 이미지 {len(manifest)}장 확인 완료")
    return manifest, is_original_report_set


def normalized_distance(left: str, right: str) -> float:
    return edit_distance(left, right) / max(len(left), len(right), 1)


def choose_consensus(outputs: dict[str, str]) -> dict:
    normalized = {
        engine: normalize(outputs.get(engine, ""))
        for engine in ENGINES
    }
    nonempty = [(engine, text) for engine, text in normalized.items() if text]
    if not nonempty:
        return {
            "chosen": "",
            "agreement": "모두 인식 실패",
            "confidence_percent": 0.0,
            "needs_review": True,
            "scorable": False,
            "normalized": normalized,
        }

    counts = Counter(text for _, text in nonempty)
    chosen, count = counts.most_common(1)[0]
    if count >= 2:
        agreement = "3개 일치" if count == 3 else "2개 일치"
        return {
            "chosen": chosen,
            "agreement": agreement,
            "confidence_percent": round(100 * count / 3, 1),
            "needs_review": False,
            "scorable": True,
            "normalized": normalized,
        }

    candidates = [text for _, text in nonempty]
    chosen = min(
        candidates,
        key=lambda candidate: sum(
            normalized_distance(candidate, other)
            for other in candidates
            if other != candidate
        ),
    )
    other_scores = [
        1 - normalized_distance(chosen, other)
        for other in candidates
        if other != chosen
    ]
    confidence = 100 * (sum(other_scores) / max(len(other_scores), 1))
    return {
        "chosen": chosen,
        "agreement": "유사도 중심값 선택",
        "confidence_percent": round(max(confidence, 0.0), 1),
        "needs_review": True,
        "scorable": True,
        "normalized": normalized,
    }


def generate_auto_labels(manifest: list[dict]) -> pd.DataFrame:
    targets = [item for item in manifest if not item.get("ground_truth")]
    if not targets:
        return pd.DataFrame()

    print(f"정답 없는 이미지 {len(targets):,}장: 3개 OCR 자동 합의 시작")
    outputs = {item["stem"]: {} for item in targets}
    for engine in ENGINES:
        print(f"  자동 정답용 {engine} 인식 중")
        model = initialize_engine(engine)
        for item in targets:
            outputs[item["stem"]][engine] = recognize(
                engine,
                model,
                SAMPLES_DIR / item["filename"],
            )
        del model
        gc.collect()

    rows = []
    scorable_count = 0
    for item in targets:
        engine_outputs = outputs[item["stem"]]
        consensus = choose_consensus(engine_outputs)
        item["ground_truth"] = consensus["chosen"]
        item["scorable"] = consensus["scorable"]
        scorable_count += int(consensus["scorable"])
        rows.append(
            {
                "filename": item["filename"],
                "condition": item["condition"],
                "tesseract_output": engine_outputs.get("Tesseract", "").replace("\n", " / "),
                "easyocr_output": engine_outputs.get("EasyOCR", "").replace("\n", " / "),
                "paddleocr_output": engine_outputs.get("PaddleOCR", "").replace("\n", " / "),
                "auto_ground_truth": consensus["chosen"],
                "agreement": consensus["agreement"],
                "confidence_percent": consensus["confidence_percent"],
                "needs_review": consensus["needs_review"],
            }
        )

    if scorable_count == 0:
        raise RuntimeError(
            "세 OCR 엔진이 모든 이미지에서 글자를 인식하지 못했습니다. "
            "이미지 해상도와 글자 영역을 확인하세요."
        )
    review_count = sum(bool(row["needs_review"]) for row in rows)
    print(
        f"자동 정답 완료: {scorable_count:,}장 채점 가능, "
        f"{review_count:,}장 검토 권장"
    )
    return pd.DataFrame(rows)


def locate_windows_tesseract() -> str | None:
    """Windows 설치 프로그램의 기본 설치 경로들을 확인합니다."""
    program_dirs = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for base in program_dirs:
        if not base:
            continue
        for sub in ("Tesseract-OCR", os.path.join("Programs", "Tesseract-OCR")):
            candidate = Path(base) / sub / "tesseract.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def validate_tesseract() -> None:
    is_windows = platform.system() == "Windows"

    if is_windows and shutil.which("tesseract") is None:
        auto_path = locate_windows_tesseract()
        if auto_path:
            pytesseract.pytesseract.tesseract_cmd = auto_path

    try:
        version = pytesseract.get_tesseract_version()
        languages = set(pytesseract.get_languages(config=""))
    except Exception as exc:
        if is_windows:
            raise RuntimeError(
                "Tesseract를 실행할 수 없습니다. "
                "https://github.com/UB-Mannheim/tesseract/wiki 에서 설치 파일을 받아 "
                "설치하세요 (설치 중 'Additional language data'에서 Korean을 꼭 선택). "
                "setup_windows.bat을 먼저 실행했는지도 확인하세요."
            ) from exc
        raise RuntimeError(
            "Tesseract를 실행할 수 없습니다. 터미널에서 "
            "'brew install tesseract tesseract-lang'을 실행하세요."
        ) from exc

    missing = {"kor", "eng"} - languages
    if missing:
        if is_windows:
            raise RuntimeError(
                f"Tesseract 언어팩이 부족합니다: {sorted(missing)}. "
                "Tesseract-OCR 설치 프로그램을 다시 실행해 'Additional language data'에서 "
                "Korean을 선택하거나, kor.traineddata 파일을 Tesseract-OCR 설치 폴더의 "
                "tessdata 폴더에 넣으세요."
            )
        raise RuntimeError(
            f"Tesseract 언어팩이 부족합니다: {sorted(missing)}. "
            "터미널에서 'brew install tesseract-lang'을 실행하세요."
        )
    print(f"Tesseract {version}")
    print(f"언어팩 확인: {', '.join(sorted(languages & {'kor', 'eng'}))}")


def preprocess(image: Image.Image, pipeline: str) -> Image.Image:
    gray = ImageOps.grayscale(image.convert("RGB"))
    gray = ImageOps.autocontrast(gray, cutoff=1)

    if pipeline == "contrast_sharpen":
        return gray.filter(
            ImageFilter.UnsharpMask(radius=1.2, percent=170, threshold=2)
        )

    if pipeline == "denoise_upscale_sharpen":
        denoised = gray.filter(ImageFilter.MedianFilter(size=3))
        enlarged = denoised.resize(
            (denoised.width * 2, denoised.height * 2),
            Image.Resampling.LANCZOS,
        )
        return enlarged.filter(
            ImageFilter.UnsharpMask(radius=1.4, percent=190, threshold=2)
        )

    raise ValueError(f"알 수 없는 전처리 방식: {pipeline}")


def paddle_result_data(result: object) -> dict:
    data = getattr(result, "json", {})
    if callable(data):
        data = data()
    if not isinstance(data, dict):
        return {}
    nested = data.get("res", data)
    return nested if isinstance(nested, dict) else {}


def build_paddleocr() -> PaddleOCR:
    return PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
        enable_mkldnn=False,  # CPU MKLDNN 충돌 방지
    )


def prepare_models() -> None:
    print("EasyOCR 한국어 영어 모델 준비 중")
    temporary_easyocr = easyocr.Reader(
        ["ko", "en"],
        gpu=False,
        verbose=False,
    )
    del temporary_easyocr
    gc.collect()

    print("PaddleOCR PP-OCRv5 모바일 모델 준비 중")
    temporary_paddleocr = build_paddleocr()
    del temporary_paddleocr
    gc.collect()
    print("모델 준비 완료")


def initialize_engine(engine: str):
    if engine == "Tesseract":
        return None
    if engine == "EasyOCR":
        return easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    if engine == "PaddleOCR":
        return build_paddleocr()
    raise ValueError(engine)


def recognize(engine: str, model, image_path: Path) -> str:
    if engine == "Tesseract":
        with Image.open(image_path) as image:
            prepared = ImageOps.autocontrast(
                ImageOps.grayscale(image.convert("RGB"))
            )
            return pytesseract.image_to_string(
                prepared,
                lang="kor+eng",
            ).strip()

    if engine == "EasyOCR":
        with Image.open(image_path) as image:
            rgb = np.asarray(image.convert("RGB"))
        lines = model.readtext(rgb, detail=0, paragraph=False)
        return "\n".join(str(line).strip() for line in lines if str(line).strip())

    if engine == "PaddleOCR":
        results = list(
            model.predict(
                input=str(image_path),
                text_rec_score_thresh=0.5,
            )
        )
        lines = []
        for result in results:
            data = paddle_result_data(result)
            lines.extend(
                str(text).strip()
                for text in data.get("rec_texts", [])
                if str(text).strip()
            )
        return "\n".join(lines)

    raise ValueError(engine)


def create_preprocessed_images(
    manifest: list[dict],
    run_root: Path,
    engine: str,
    run_number: int,
) -> tuple[Path, float]:
    output_dir = run_root / "_임시_전처리" / f"{engine}_{run_number:02d}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for item in manifest:
        with Image.open(SAMPLES_DIR / item["filename"]) as image:
            processed = preprocess(image, PIPELINES[engine]["name"])
            processed.save(output_dir / item["filename"])
    return output_dir, time.perf_counter() - started


def evaluate_rows(
    manifest: list[dict],
    engine: str,
    run_number: int,
    phase: str,
    recognized_lookup: dict[str, str],
) -> tuple[dict, list[dict]]:
    exact_matches = 0
    total_errors = 0
    total_characters = 0
    evaluated_images = 0
    rows = []

    for item in manifest:
        scorable = bool(item.get("scorable", True))
        truth = normalize(item.get("ground_truth") or "")
        raw = recognized_lookup[item["stem"]]
        recognized = normalize(raw)
        distance = edit_distance(truth, recognized) if scorable else None
        exact = (recognized == truth) if scorable else None

        if scorable:
            evaluated_images += 1
            exact_matches += int(exact)
            total_errors += int(distance)
            total_characters += len(truth)
        rows.append(
            {
                "phase": phase,
                "run": run_number,
                "engine": engine,
                "sample": item["stem"],
                "condition": item["condition"],
                "ground_truth": truth,
                "raw_output": raw.replace("\n", " / "),
                "normalized_output": recognized,
                "exact_match": exact,
                "character_errors": distance,
                "cer_percent": (
                    round(100 * int(distance) / max(len(truth), 1), 3)
                    if scorable
                    else None
                ),
                "answer_source": item.get("answer_source", "기본 정답"),
            }
        )

    return (
        {
            "exact_matches": exact_matches,
            "evaluated_images": evaluated_images,
            "accuracy_percent": round(
                100 * exact_matches / max(evaluated_images, 1),
                3,
            ),
            "cer_percent": round(
                100 * total_errors / max(total_characters, 1),
                3,
            ),
        },
        rows,
    )


def run_engine_batch(
    manifest: list[dict],
    engine: str,
    run_number: int,
    phase: str,
    image_dir: Path,
    preprocessing_seconds: float,
) -> tuple[dict, list[dict]]:
    started = time.perf_counter()
    model = initialize_engine(engine)
    recognized_lookup = {}

    for item in manifest:
        image_path = image_dir / item["filename"]
        raw = recognize(engine, model, image_path)
        recognized_lookup[item["stem"]] = raw

    ocr_seconds = time.perf_counter() - started
    metrics, sample_rows = evaluate_rows(
        manifest,
        engine,
        run_number,
        phase,
        recognized_lookup,
    )

    del model
    gc.collect()

    return (
        {
            "phase": phase,
            "run": run_number,
            "engine": engine,
            "preprocessing_seconds": round(preprocessing_seconds, 6),
            "ocr_seconds": round(ocr_seconds, 6),
            "total_seconds": round(preprocessing_seconds + ocr_seconds, 6),
            **metrics,
        },
        sample_rows,
    )


def run_benchmark(
    manifest: list[dict],
    run_root: Path,
    phase: str,
    repetitions: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_rows = []
    sample_rows = []

    for run_number in range(1, repetitions + 1):
        order = ENGINE_ORDERS[(run_number - 1) % len(ENGINE_ORDERS)]
        phase_label = PHASE_LABELS[phase]
        print(f"[{phase_label} {run_number:02d}/{repetitions}] {' -> '.join(order)}")

        for engine in order:
            if phase == "preprocessed":
                image_dir, preprocessing_seconds = create_preprocessed_images(
                    manifest,
                    run_root,
                    engine,
                    run_number,
                )
            else:
                image_dir = SAMPLES_DIR
                preprocessing_seconds = 0.0

            run_row, current_samples = run_engine_batch(
                manifest,
                engine,
                run_number,
                phase,
                image_dir,
                preprocessing_seconds,
            )
            run_rows.append(run_row)
            if run_number == 1:
                sample_rows.extend(current_samples)
            if phase == "preprocessed":
                shutil.rmtree(image_dir)
            print(
                f"  {engine}: {run_row['exact_matches']}/{run_row['evaluated_images']}, "
                f"CER {run_row['cer_percent']:.1f}%, "
                f"총 {run_row['total_seconds']:.3f}초"
            )

    return pd.DataFrame(run_rows), pd.DataFrame(sample_rows)


def phase_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    return (
        run_df.groupby("engine", sort=False)
        .agg(
            exact_matches=("exact_matches", "mean"),
            evaluated_images=("evaluated_images", "mean"),
            accuracy_percent=("accuracy_percent", "mean"),
            cer_percent=("cer_percent", "mean"),
            mean_total_seconds=("total_seconds", "mean"),
            median_total_seconds=("total_seconds", "median"),
            min_total_seconds=("total_seconds", "min"),
            max_total_seconds=("total_seconds", "max"),
            stdev_total_seconds=("total_seconds", "std"),
            mean_preprocessing_seconds=("preprocessing_seconds", "mean"),
        )
        .reset_index()
    )


def build_comparisons(
    baseline_runs: pd.DataFrame,
    baseline_samples: pd.DataFrame,
    preprocessed_runs: pd.DataFrame,
    preprocessed_samples: pd.DataFrame,
    include_report_reference: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    before = phase_summary(baseline_runs).add_prefix("before_")
    before = before.rename(columns={"before_engine": "engine"})
    after = phase_summary(preprocessed_runs).add_prefix("after_")
    after = after.rename(columns={"after_engine": "engine"})
    summary = before.merge(after, on="engine")

    summary["accuracy_change_percentage_points"] = (
        summary["after_accuracy_percent"] - summary["before_accuracy_percent"]
    )
    summary["cer_change_percentage_points"] = (
        summary["after_cer_percent"] - summary["before_cer_percent"]
    )
    summary["speed_change_percent"] = 100 * (
        summary["after_mean_total_seconds"]
        - summary["before_mean_total_seconds"]
    ) / summary["before_mean_total_seconds"]
    numeric_columns = summary.select_dtypes(include=["number"]).columns
    summary[numeric_columns] = summary[numeric_columns].round(3)

    before_first = baseline_samples[baseline_samples["run"] == 1]
    after_first = preprocessed_samples[preprocessed_samples["run"] == 1]
    condition_before = (
        baseline_samples.groupby(["condition", "engine"], sort=False)["exact_match"]
        .mean()
        .mul(100)
        .rename("before_accuracy_percent")
        .reset_index()
    )
    condition_after = (
        preprocessed_samples.groupby(["condition", "engine"], sort=False)["exact_match"]
        .mean()
        .mul(100)
        .rename("after_accuracy_percent")
        .reset_index()
    )
    condition_comparison = condition_before.merge(
        condition_after,
        on=["condition", "engine"],
    )
    condition_comparison["change_percentage_points"] = (
        condition_comparison["after_accuracy_percent"]
        - condition_comparison["before_accuracy_percent"]
    )
    condition_comparison[
        [
            "before_accuracy_percent",
            "after_accuracy_percent",
            "change_percentage_points",
        ]
    ] = condition_comparison[
        [
            "before_accuracy_percent",
            "after_accuracy_percent",
            "change_percentage_points",
        ]
    ].round(3)

    sample_comparison = before_first[
        [
            "engine",
            "sample",
            "condition",
            "ground_truth",
            "answer_source",
            "normalized_output",
            "exact_match",
        ]
    ].merge(
        after_first[["engine", "sample", "normalized_output", "exact_match"]],
        on=["engine", "sample"],
        suffixes=("_before", "_after"),
    )
    sample_comparison["change"] = np.select(
        [
            sample_comparison["exact_match_before"].isna()
            | sample_comparison["exact_match_after"].isna(),
            sample_comparison["exact_match_before"].eq(False)
            & sample_comparison["exact_match_after"].eq(True),
            sample_comparison["exact_match_before"].eq(True)
            & sample_comparison["exact_match_after"].eq(False),
        ],
        ["검토필요", "개선", "악화"],
        default="동일",
    )

    if not include_report_reference:
        return summary, condition_comparison, sample_comparison, pd.DataFrame()

    report_reference = pd.DataFrame(
        [
            {
                "engine": "Tesseract",
                "report_before_correct": 17,
                "report_after_correct": 22,
                "report_before_accuracy": 56.7,
                "report_after_accuracy": 73.3,
                "report_before_cer": 22.4,
                "report_after_cer": 10.5,
                "report_before_seconds": 5.768,
                "report_after_seconds": 7.030,
            },
            {
                "engine": "EasyOCR",
                "report_before_correct": 23,
                "report_after_correct": 25,
                "report_before_accuracy": 76.7,
                "report_after_accuracy": 83.3,
                "report_before_cer": 3.3,
                "report_after_cer": None,
                "report_before_seconds": 12.127,
                "report_after_seconds": 12.166,
            },
            {
                "engine": "PaddleOCR",
                "report_before_correct": 27,
                "report_after_correct": 27,
                "report_before_accuracy": 90.0,
                "report_after_accuracy": 90.0,
                "report_before_cer": 1.4,
                "report_after_cer": None,
                "report_before_seconds": 6.476,
                "report_after_seconds": 6.540,
            },
        ]
    )
    measured = summary[
        [
            "engine",
            "before_exact_matches",
            "after_exact_matches",
            "before_accuracy_percent",
            "after_accuracy_percent",
            "before_cer_percent",
            "after_cer_percent",
            "before_mean_total_seconds",
            "after_mean_total_seconds",
        ]
    ]
    report_vs_measured = report_reference.merge(measured, on="engine")
    return summary, condition_comparison, sample_comparison, report_vs_measured


def save_results(
    run_root: Path,
    repetitions: int,
    image_count: int,
    baseline_runs: pd.DataFrame,
    baseline_samples: pd.DataFrame,
    preprocessed_runs: pd.DataFrame,
    preprocessed_samples: pd.DataFrame,
    summary: pd.DataFrame,
    condition_comparison: pd.DataFrame,
    sample_comparison: pd.DataFrame,
    report_vs_measured: pd.DataFrame,
    auto_labels: pd.DataFrame,
    label_mode: str,
) -> Path:
    return save_korean_results(
        run_root,
        repetitions,
        image_count,
        baseline_runs,
        preprocessed_runs,
        summary,
        condition_comparison,
        sample_comparison,
        report_vs_measured,
        auto_labels,
        label_mode,
    )


def main() -> int:
    arguments = parse_arguments()
    if arguments.repetitions < 1:
        raise ValueError("반복 횟수는 1 이상이어야 합니다.")

    manifest, is_original_report_set = load_manifest()
    validate_tesseract()
    prepare_models()

    if arguments.prepare_models:
        return 0

    run_root = RESULTS_ROOT / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=False)
    print(f"결과 폴더: {run_root}")

    auto_labels = generate_auto_labels(manifest)
    has_auto_labels = not auto_labels.empty
    has_provided_labels = any(
        item.get("answer_source") != "자동 합의" for item in manifest
    )
    if has_auto_labels and has_provided_labels:
        label_mode = "실제 정답 + 자동 합의 혼합"
    elif has_auto_labels:
        label_mode = "3개 OCR 자동 합의"
    else:
        label_mode = "제공된 실제 정답"

    baseline_runs, baseline_samples = run_benchmark(
        manifest,
        run_root,
        "baseline",
        arguments.repetitions,
    )
    preprocessed_runs, preprocessed_samples = run_benchmark(
        manifest,
        run_root,
        "preprocessed",
        arguments.repetitions,
    )
    (
        summary,
        condition_comparison,
        sample_comparison,
        report_vs_measured,
    ) = build_comparisons(
        baseline_runs,
        baseline_samples,
        preprocessed_runs,
        preprocessed_samples,
        is_original_report_set,
    )
    archive = save_results(
        run_root,
        arguments.repetitions,
        len(manifest),
        baseline_runs,
        baseline_samples,
        preprocessed_runs,
        preprocessed_samples,
        summary,
        condition_comparison,
        sample_comparison,
        report_vs_measured,
        auto_labels,
        label_mode,
    )

    score_label = (
        "자동합의 일치율(%)"
        if "자동 합의" in label_mode
        else "정확도(%)"
    )
    console_summary = summary[
        [
            "engine",
            "before_exact_matches",
            "after_exact_matches",
            "before_accuracy_percent",
            "after_accuracy_percent",
            "before_cer_percent",
            "after_cer_percent",
            "before_mean_total_seconds",
            "after_mean_total_seconds",
        ]
    ].rename(
        columns={
            "engine": "OCR 엔진",
            "before_exact_matches": "전처리 전 일치 수",
            "after_exact_matches": "전처리 후 일치 수",
            "before_accuracy_percent": f"전처리 전 {score_label}",
            "after_accuracy_percent": f"전처리 후 {score_label}",
            "before_cer_percent": "전처리 전 CER(%)",
            "after_cer_percent": "전처리 후 CER(%)",
            "before_mean_total_seconds": "전처리 전 평균시간(초)",
            "after_mean_total_seconds": "전처리 후 평균시간(초)",
        }
    )
    print(f"\n전처리 전후 종합 결과 · 기준: {label_mode}")
    print(console_summary.to_string(index=False))
    print(f"\n완료 폴더: {run_root}")
    print(f"완료 ZIP: {archive}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n사용자가 실행을 중단했습니다.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n실행 오류: {exc}", file=sys.stderr)
        raise