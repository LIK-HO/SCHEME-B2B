from __future__ import annotations

import logging
import uuid

from .airtable import AirtableClient
from .config import Settings
from .db import (
    LeaseBusyError,
    acquire_lease,
    claim_company_identity,
    create_session_factory,
    mark_company_identity_projected,
    release_lease,
)
from .dedup import GlobalDeduplicator
from .fns import FNSVerifier
from .models import RunItem, RunLog
from .outbox import CHANNEL_EMAIL, CHANNEL_MAX, OutboxDispatcher
from .schedule import already_ran_this_slot, next_run, should_run_now
from .scoring import priority
from .sources import Candidate, CandidateSource, build_sources
from .time_utils import now_msk, now_utc
from .validation import validate_requisites


logger = logging.getLogger(__name__)


class SearchService:
    def __init__(
        self,
        settings: Settings,
        airtable: AirtableClient,
        sources: list[CandidateSource] | None = None,
    ):
        self.settings = settings
        self.airtable = airtable
        self.sources = sources if sources is not None else build_sources(settings)
        self.fns = FNSVerifier(settings)
        self.dedup = GlobalDeduplicator(
            airtable,
            settings.airtable_table_companies,
            settings.airtable_table_clients,
            settings.airtable_table_archive,
        )
        self.outbox = OutboxDispatcher(airtable, settings)
        self.session_factory = create_session_factory(settings)

    def run_once(self, manual: bool = False) -> dict[str, object]:
        profile = self.airtable.get_search_profile(self.settings)
        if not manual and not profile:
            raise RuntimeError(f"Профиль поиска '{self.settings.search_profile_name}' не найден")

        if not manual and not self._profile_allows_run(profile):
            return {"status": "skipped", "reason": "outside_schedule_or_disabled"}

        run_id = f"run-{now_msk().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        try:
            lease_owner = acquire_lease(
                self.session_factory,
                "search-run",
                self.settings.search_lease_seconds,
            )
        except LeaseBusyError:
            return {"status": "skipped", "reason": "another_search_worker_is_running"}

        try:
            log = RunLog(run_id=run_id, status="started", started_at=now_utc())
            with self.session_factory() as session:
                session.add(log)
                session.commit()
        except Exception:
            release_lease(self.session_factory, "search-run", lease_owner)
            raise

        try:
            counters = {
                "candidates": 0,
                "inserted": 0,
                "duplicates": 0,
                "rejected": 0,
                "errors": 0,
            }
            source_errors: list[str] = []
            rejected_reasons: dict[str, int] = {}
            duplicate_locations: dict[str, list[str]] = {}
            seen_batch: set[str] = set()
            source_limits_hit: list[str] = []
            new_limit_hit = False

            if not self.sources:
                source_errors.append("Источники поиска не настроены")
                counters["errors"] = 1
                summary = self._summary_text(
                    run_id,
                    counters,
                    duplicate_locations,
                    rejected_reasons,
                    source_errors,
                    source_limits_hit,
                    new_limit_hit,
                )
                try:
                    self._enqueue_summary(profile, run_id, summary)
                except Exception as exc:
                    counters["errors"] += 1
                    source_errors.append(f"Создание уведомления: {exc}")
                    summary = self._summary_text(
                        run_id,
                        counters,
                        duplicate_locations,
                        rejected_reasons,
                        source_errors,
                        source_limits_hit,
                        new_limit_hit,
                    )
                self._update_run_log(run_id, "error", counters, summary)
                return {"status": "error", "run_id": run_id, **counters, "summary": summary}

            try:
                self.dedup.prime()
            except Exception as exc:
                source_errors.append(f"Дедупликация Airtable: {exc}")
                counters["errors"] = 1
                summary = self._summary_text(
                    run_id,
                    counters,
                    duplicate_locations,
                    rejected_reasons,
                    source_errors,
                    source_limits_hit,
                    new_limit_hit,
                )
                try:
                    self._enqueue_summary(profile, run_id, summary)
                except Exception as exc:
                    counters["errors"] += 1
                    source_errors.append(f"Создание уведомления: {exc}")
                    summary = self._summary_text(
                        run_id,
                        counters,
                        duplicate_locations,
                        rejected_reasons,
                        source_errors,
                        source_limits_hit,
                        new_limit_hit,
                    )
                self._update_run_log(run_id, "error", counters, summary)
                return {"status": "error", "run_id": run_id, **counters, "summary": summary}

            stop_after_new = False
            for source in self.sources:
                source_seen = 0
                try:
                    for candidate in source.iter_candidates():
                        if source_seen >= self.settings.max_candidates_per_source:
                            source_limits_hit.append(source.name)
                            break
                        source_seen += 1
                        counters["candidates"] += 1

                        self._process_candidate(
                            run_id,
                            candidate,
                            source.name,
                            seen_batch,
                            counters,
                            duplicate_locations,
                            rejected_reasons,
                        )

                        if counters["inserted"] >= self.settings.max_new_records_per_run:
                            new_limit_hit = True
                            stop_after_new = True
                            break
                except Exception as exc:
                    source_errors.append(f"{source.name}: {exc}")
                    counters["errors"] += 1

                if stop_after_new:
                    break

            run_status = (
                "partial" if source_errors or source_limits_hit or new_limit_hit or counters["errors"] else "success"
            )

            if profile:
                try:
                    self._mark_profile_run(profile)
                except Exception as exc:
                    counters["errors"] += 1
                    source_errors.append(f"Обновление профиля поиска: {exc}")
                    run_status = "partial"

            summary = self._summary_text(
                run_id,
                counters,
                duplicate_locations,
                rejected_reasons,
                source_errors,
                source_limits_hit,
                new_limit_hit,
            )

            try:
                self._enqueue_summary(profile, run_id, summary)
            except Exception as exc:
                counters["errors"] += 1
                source_errors.append(f"Создание уведомления: {exc}")
                run_status = "partial"
                summary = self._summary_text(
                    run_id,
                    counters,
                    duplicate_locations,
                    rejected_reasons,
                    source_errors,
                    source_limits_hit,
                    new_limit_hit,
                )

            self._update_run_log(run_id, run_status, counters, summary)
            return {"status": run_status, "run_id": run_id, **counters, "summary": summary}

        except Exception as exc:
            summary = f"Запуск {run_id} завершён с ошибкой: {exc}"
            try:
                self._update_run_log(run_id, "error", {"errors": 1}, summary)
            except Exception:
                logger.exception("Failed to persist error state for run: %s", run_id)
            logger.exception("Search run failed: %s", run_id)
            raise
        finally:
            release_lease(self.session_factory, "search-run", lease_owner)

    def _process_candidate(
        self,
        run_id: str,
        candidate: Candidate,
        source_name: str,
        seen_batch: set[str],
        counters: dict[str, int],
        duplicate_locations: dict[str, list[str]],
        rejected_reasons: dict[str, int],
    ) -> None:
        try:
            effective_source = candidate.source or source_name
            if not candidate.company:
                counters["rejected"] += 1
                rejected_reasons["Название компании отсутствует"] = (
                    rejected_reasons.get("Название компании отсутствует", 0) + 1
                )
                return

            validation = validate_requisites(candidate.inn, candidate.ogrn, candidate.ogrnip)
            inn = validation.inn
            if not validation.valid:
                counters["rejected"] += 1
                rejected_reasons[validation.reason] = rejected_reasons.get(validation.reason, 0) + 1
                return

            if inn in seen_batch:
                counters["duplicates"] += 1
                duplicate_locations.setdefault(inn, []).append("текущий запуск")
                return

            dedup = self.dedup.check(inn)
            if dedup.duplicate:
                counters["duplicates"] += 1
                duplicate_locations[inn] = list(dedup.locations)
                return

            fns = self.fns.verify(inn, validation.ogrn, validation.ogrnip)
            if self.settings.require_fns_confirmation and not fns.confirmed:
                if fns.status == "Ошибка":
                    counters["errors"] += 1
                    rejected_reasons[f"Проверка ФНС: {fns.message}"] = (
                        rejected_reasons.get(f"Проверка ФНС: {fns.message}", 0) + 1
                    )
                    return
                seen_batch.add(inn)
                counters["rejected"] += 1
                rejected_reasons[fns.message] = rejected_reasons.get(fns.message, 0) + 1
                return

            seen_batch.add(inn)
            level, score = priority(candidate, validation, fns.confirmed)
            comment_parts = [
                candidate.comment,
                f"Автооценка: {score}/100",
                f"ФНС: {fns.status}",
            ]

            company_fields = {
                "Компания": candidate.company,
                "ИНН": inn,
                "ОГРН": validation.ogrn,
                "ОГРНИП": validation.ogrnip,
                "Город": candidate.city,
                "Сфера": candidate.sector,
                "Потребность": candidate.need,
                "Телефон": candidate.phone,
                "Почта": candidate.email,
                "Сайт": candidate.website,
                "Ответственный": candidate.responsible,
                "Статус": "Ожидает",
                "Источник": effective_source,
                "Приоритет": level,
                "Дата обнаружения": now_msk().date().isoformat(),
                "Дата проверки": now_msk().date().isoformat(),
                "Комментарий": "; ".join(x for x in comment_parts if x),
                "Проверка ФНС": fns.status,
                "Дата проверки ФНС": now_msk().date().isoformat(),
                "Источник проверки ФНС": fns.source_url,
                "Результат проверки ФНС": fns.message,
            }
            claimed, identity = claim_company_identity(
                self.session_factory,
                inn,
                run_id,
                effective_source,
            )
            if not claimed and identity.status != "projection_pending":
                counters["duplicates"] += 1
                duplicate_locations.setdefault(inn, []).append("core identity")
                return

            airtable_record_id = ""
            outcome = "created"
            try:
                result = self.airtable.create_record(
                    self.settings.airtable_table_companies,
                    company_fields,
                )
                airtable_record_id = str(result.get("id") or "") if isinstance(result, dict) else ""
            except Exception as exc:
                try:
                    existing = self.airtable.find_first_by_inn(
                        self.settings.airtable_table_companies,
                        inn,
                    )
                    if not existing:
                        raise exc
                    airtable_record_id = str(existing.get("id") or "")
                    outcome = "reconciled"
                    logger.warning(
                        "Airtable create outcome ambiguous; record already exists for INN %s",
                        inn,
                    )
                except Exception:
                    raise

            mark_company_identity_projected(
                self.session_factory,
                inn,
                airtable_record_id,
            )
            self._record_run_item(
                run_id,
                inn,
                effective_source,
                outcome,
                airtable_record_id,
            )
            counters["inserted"] += 1

        except Exception:
            counters["errors"] += 1
            logger.exception("Ошибка обработки кандидата %s", candidate.company)

    def _record_run_item(
        self,
        run_id: str,
        inn: str,
        source: str,
        outcome: str,
        airtable_record_id: str,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                RunItem(
                    run_id=run_id,
                    inn=inn,
                    source=source,
                    outcome=outcome,
                    airtable_record_id=airtable_record_id,
                )
            )
            session.commit()

    def dispatch_outbox(self) -> dict[str, int]:
        try:
            lease_owner = acquire_lease(
                self.session_factory,
                "outbox-dispatch",
                self.settings.outbox_lease_seconds,
            )
        except LeaseBusyError:
            return {"sent": 0, "failed": 0, "skipped": 0, "locked": 1}
        try:
            return self.outbox.dispatch()
        finally:
            release_lease(self.session_factory, "outbox-dispatch", lease_owner)

    def _notification_channels(self, profile: dict | None) -> list[tuple[str, str]]:
        fields = profile.get("fields", {}) if profile else {}
        channels: list[tuple[str, str]] = []

        email_enabled = bool(fields.get("Email уведомления")) if profile else self.settings.email_enabled
        email_to = str(fields.get("Email получатель") or self.settings.email_to)
        if email_enabled and email_to:
            channels.append((CHANNEL_EMAIL, email_to))

        max_enabled = bool(fields.get("MAX уведомления")) if profile else self.settings.max_enabled
        max_recipient = str(fields.get("MAX получатель (ID)") or self.settings.max_recipient_id)
        if max_enabled and max_recipient:
            channels.append((CHANNEL_MAX, max_recipient))

        return channels

    def _enqueue_summary(self, profile: dict | None, run_id: str, summary: str) -> None:
        profile_fields = profile.get("fields", {}) if profile else {}
        profile_name = str(profile_fields.get("Профиль поиска") or self.settings.search_profile_name)
        for channel, recipient in self._notification_channels(profile):
            self.outbox.enqueue(
                f"{run_id}:summary:{channel}",
                channel,
                profile_name,
                summary,
                recipient,
            )

    def _profile_allows_run(self, profile: dict) -> bool:
        fields = profile.get("fields", {})
        if not bool(fields.get("Активен")) or not bool(fields.get("Автопоиск")):
            return False

        frequency = str(fields.get("Частота поиска") or "1 раз в день")
        now = now_msk()
        if not should_run_now(frequency, now):
            return False

        last_run = fields.get("Последний запуск")
        return not already_ran_this_slot(str(last_run) if last_run else None, now)

    def _mark_profile_run(self, profile: dict) -> None:
        now = now_msk()
        upcoming = next_run(
            str(profile.get("fields", {}).get("Частота поиска") or "1 раз в день"),
            now,
        )
        self.airtable.update_record(
            self.settings.airtable_table_search,
            profile["id"],
            {
                "Последний запуск": now.isoformat(timespec="seconds"),
                "Следующий запуск": upcoming.isoformat(timespec="seconds"),
            },
        )

    def _update_run_log(
        self,
        run_id: str,
        status: str,
        counters: dict[str, int],
        details: str,
    ) -> None:
        with self.session_factory() as session:
            log = session.query(RunLog).filter_by(run_id=run_id).one()
            log.status = status
            log.finished_at = now_utc()
            for key in ("candidates", "inserted", "duplicates", "rejected", "errors"):
                if key in counters:
                    setattr(log, key, counters[key])
            log.details = details[:10000]
            session.commit()

    @staticmethod
    def _summary_text(
        run_id: str,
        counters: dict[str, int],
        duplicate_locations: dict[str, list[str]],
        rejected_reasons: dict[str, int],
        source_errors: list[str],
        source_limits_hit: list[str],
        new_limit_hit: bool,
    ) -> str:
        lines = [
            f"Запуск: {run_id}",
            f"Кандидатов: {counters.get('candidates', 0)}",
            f"Новых компаний: {counters.get('inserted', 0)}",
            f"Дубликатов: {counters.get('duplicates', 0)}",
            f"Отклонено: {counters.get('rejected', 0)}",
            f"Ошибок: {counters.get('errors', 0)}",
        ]
        if source_limits_hit:
            lines.append("Лимит источника достигнут: " + ", ".join(source_limits_hit[:20]))
        if new_limit_hit:
            lines.append("Лимит новых компаний за запуск достигнут")
        if duplicate_locations:
            lines.append("Дедуп:")
            for inn, locations in list(duplicate_locations.items())[:20]:
                lines.append(f"- {inn}: {', '.join(locations)}")
        if rejected_reasons:
            lines.append("Причины отклонения:")
            for reason, count in list(rejected_reasons.items())[:20]:
                lines.append(f"- {count} × {reason}")
        if source_errors:
            lines.append("Ошибки источников:")
            lines.extend(f"- {x}" for x in source_errors[:20])
        return "\n".join(lines)
