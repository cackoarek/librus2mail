import html
from datetime import datetime


class MailSender:
    def __init__(self, mail_config):
        self.sender_email = mail_config['login']
        self.password = mail_config['password']

    @staticmethod
    def create_mail_content_for_messages(user_config: dict, messages: list) -> str:
        contents = f"""
            <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe wiadomości</strong>.</p>
            <p>&nbsp;</p>
            <p>Lista wszystkich wiadomości (nowe <strong>boldem</strong>):</p>
            <table border="1" cellspacing="0" cellpadding="10">
            <thead><tr><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
            <tbody>
            """

        for message in messages:
            if message['is_unread']:
                contents += f"""
                    <tr>
                    <td><strong>{message['title']}</strong></td>
                    <td><strong>{message['sender']}</strong></td>
                    <td><strong>{message['datetime']}</strong></td>"""
                if 'body' in message:
                    body = message['body'].replace("\n", "<br>")
                    contents += f"""</tr><tr><td colspan="3">{body}</td>"""
                contents += '</tr>'
            else:
                contents += f"""
                    <tr>
                    <td>{message['title']}</td>
                    <td>{message['sender']}</td>
                    <td>{message['datetime']}</td>
                    </tr>
                    """

        contents += "</tbody></table>"
        return contents

    @staticmethod
    def create_mail_content_for_notifications(user_config: dict, notifications: list) -> str:
        contents = f"""
                <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe ogłoszenia</strong>.</p>
                <p>&nbsp;</p>
                <p>Lista wszystkich ogłoszeń (nowe <strong>boldem</strong>):</p>
                <table border="1" cellspacing="0" cellpadding="10">
                <thead><tr><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
                <tbody>
                """

        for notification in notifications:
            if notification['is_unread']:
                contents += f"""
                        <tr>
                        <td><strong>{notification['title']}</strong></td>
                        <td><strong>{notification['sender']}</strong></td>
                        <td><strong>{notification['datetime']}</strong></td>"""
                if 'body' in notification:
                    body = notification['body'].replace("\n", "<br>")
                    contents += f"""</tr><tr><td colspan="3">{body}</td>"""
                contents += '</tr>'
            else:
                contents += f"""
                        <tr>
                        <td>{notification['title']}</td>
                        <td>{notification['sender']}</td>
                        <td>{notification['datetime']}</td>
                        </tr>
                        """

        contents += "</tbody></table>"
        return contents

    @staticmethod
    def create_mail_content_for_grades(user_config: dict, grades: list) -> str:
        contents = f"""
            <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe oceny</strong>.</p>
            <p>&nbsp;</p>
            <table border="1" cellspacing="0" cellpadding="8" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
            <thead>
                <tr style="background-color: #f2f2f2; text-align: left;">
                    <th>Przedmiot</th>
                    <th style="text-align: center;">Ocena</th>
                    <th>Kategoria</th>
                    <th style="text-align: center;">Waga</th>
                    <th>Data</th>
                    <th>Nauczyciel</th>
                    <th>Komentarz</th>
                </tr>
            </thead>
            <tbody>
            """

        for grade in grades:
            weight = grade.get('weight') or '-'
            date = grade.get('date') or '-'
            teacher = grade.get('teacher') or '-'
            category = grade.get('category') or '-'
            comment = grade.get('comment') or '-'
            contents += f"""
                <tr>
                    <td><strong>{grade['subject']}</strong></td>
                    <td style="text-align: center; font-size: 16px;"><strong>{grade['grade']}</strong></td>
                    <td>{category}</td>
                    <td style="text-align: center;">{weight}</td>
                    <td>{date}</td>
                    <td>{teacher}</td>
                    <td>{comment}</td>
                </tr>
                """

        contents += "</tbody></table>"
        return contents

    @staticmethod
    def _create_summary_title(user_config: dict, messages: list, notifications: list, grades: list) -> str:
        parts = []
        if messages:
            count = len(messages)
            if count == 1:
                parts.append("1 nowa wiadomość")
            elif 2 <= count <= 4 or (count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
                parts.append(f"{count} nowe wiadomości")
            else:
                parts.append(f"{count} nowych wiadomości")

        if notifications:
            count = len(notifications)
            if count == 1:
                parts.append("1 nowe ogłoszenie")
            elif 2 <= count <= 4 or (count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
                parts.append(f"{count} nowe ogłoszenia")
            else:
                parts.append(f"{count} nowych ogłoszeń")

        if grades:
            grades_summary = ", ".join([f"{g['subject']}: {g['grade']}" for g in grades[:2]])
            if len(grades) > 2:
                grades_summary += f" (+{len(grades) - 2})"
            parts.append(f"nowe oceny ({grades_summary})")

        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        if not parts:
            return f"{name} - Librus: podsumowanie"
        return f"{name} - Librus: " + ", ".join(parts)

    @staticmethod
    def create_mail_content_for_summary(
        user_config: dict,
        messages: list = None,
        notifications: list = None,
        grades: list = None
    ) -> str:
        messages = messages or []
        notifications = notifications or []
        grades = grades or []

        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        login = user_config.get('librus_login', '')

        contents = f"""
        <p>Zbiorcze powiadomienie z Librusa dla konta {login} <strong>({name})</strong>.</p>
        <p>&nbsp;</p>
        """

        if messages:
            contents += f"""
            <h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin-top: 20px;">Nowe wiadomości ({len(messages)})</h3>
            <table border="1" cellspacing="0" cellpadding="10" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
            <thead><tr style="background-color: #f2f2f2; text-align: left;"><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
            <tbody>
            """
            for message in messages:
                contents += f"""
                    <tr>
                    <td><strong>{message['title']}</strong></td>
                    <td><strong>{message['sender']}</strong></td>
                    <td><strong>{message['datetime']}</strong></td></tr>"""
                if 'body' in message:
                    body = message['body'].replace("\n", "<br>")
                    contents += f"""<tr><td colspan="3" style="background-color: #fcfcfc;">{body}</td></tr>"""
            contents += "</tbody></table><p>&nbsp;</p>"

        if notifications:
            contents += f"""
            <h3 style="color: #2c3e50; border-bottom: 2px solid #e67e22; padding-bottom: 5px; margin-top: 20px;">Nowe ogłoszenia ({len(notifications)})</h3>
            <table border="1" cellspacing="0" cellpadding="10" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
            <thead><tr style="background-color: #f2f2f2; text-align: left;"><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
            <tbody>
            """
            for notification in notifications:
                contents += f"""
                    <tr>
                    <td><strong>{notification['title']}</strong></td>
                    <td><strong>{notification['sender']}</strong></td>
                    <td><strong>{notification['datetime']}</strong></td></tr>"""
                if 'body' in notification:
                    body = notification['body'].replace("\n", "<br>")
                    contents += f"""<tr><td colspan="3" style="background-color: #fcfcfc;">{body}</td></tr>"""
            contents += "</tbody></table><p>&nbsp;</p>"

        if grades:
            contents += f"""
            <h3 style="color: #2c3e50; border-bottom: 2px solid #27ae60; padding-bottom: 5px; margin-top: 20px;">Nowe oceny ({len(grades)})</h3>
            <table border="1" cellspacing="0" cellpadding="8" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
            <thead>
                <tr style="background-color: #f2f2f2; text-align: left;">
                    <th>Przedmiot</th>
                    <th style="text-align: center;">Ocena</th>
                    <th>Kategoria</th>
                    <th style="text-align: center;">Waga</th>
                    <th>Data</th>
                    <th>Nauczyciel</th>
                    <th>Komentarz</th>
                </tr>
            </thead>
            <tbody>
            """
            for grade in grades:
                weight = grade.get('weight') or '-'
                date = grade.get('date') or '-'
                teacher = grade.get('teacher') or '-'
                category = grade.get('category') or '-'
                comment = grade.get('comment') or '-'
                contents += f"""
                    <tr>
                        <td><strong>{grade['subject']}</strong></td>
                        <td style="text-align: center; font-size: 16px;"><strong>{grade['grade']}</strong></td>
                        <td>{category}</td>
                        <td style="text-align: center;">{weight}</td>
                        <td>{date}</td>
                        <td>{teacher}</td>
                        <td>{comment}</td>
                    </tr>
                    """
            contents += "</tbody></table><p>&nbsp;</p>"

        return contents

    def send_mail_with_messages(self, user_config, messages):
        pass

    def send_mail_with_notifications(self, user_config, notifications):
        pass

    def send_mail_with_grades(self, user_config, grades):
        pass

    def send_mail_with_summary(self, user_config, messages=None, notifications=None, grades=None):
        pass

    @staticmethod
    def _format_grade_badge(val: str) -> str:
        s = str(val).strip()
        first_char = s[0] if s else ''
        if first_char in ('5', '6'):
            bg = "#d1fae5"
            color = "#065f46"
            border = "#a7f3d0"
        elif first_char == '4':
            bg = "#dbeafe"
            color = "#1e40af"
            border = "#bfdbfe"
        elif first_char == '3':
            bg = "#fef3c7"
            color = "#92400e"
            border = "#fde68a"
        elif first_char in ('1', '2'):
            bg = "#fee2e2"
            color = "#991b1b"
            border = "#fecaca"
        else:
            bg = "#f3f4f6"
            color = "#374151"
            border = "#e5e7eb"
        return f'<span style="display: inline-block; background-color: {bg}; color: {color}; border: 1px solid {border}; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 13px; margin: 1px;">{html.escape(s)}</span>'

    @classmethod
    def _create_progress_report_title(cls, user_config: dict, analysis: dict) -> str:
        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        p_start = analysis.get('period_start_str', '')
        p_end = analysis.get('period_end_str', '')
        overall_avg = analysis.get('overall_avg')
        avg_text = f"śr. {overall_avg:.2f}" if overall_avg is not None else "brak średniej"
        period_count = analysis.get('period_grades_count', 0)
        return f"📊 Raport postępów: {name} ({p_start} – {p_end}) [{avg_text}, nowe oceny: {period_count}]"

    @classmethod
    def create_mail_content_for_progress_report(cls, user_config: dict, analysis: dict) -> str:
        name = html.escape(str(user_config.get('librus_login_name') or user_config.get('librus_login', '')))
        login = html.escape(str(user_config.get('librus_login', '')))
        p_start = analysis.get('period_start_str', '')
        p_end = analysis.get('period_end_str', '')
        overall_avg = analysis.get('overall_avg')
        period_avg = analysis.get('period_avg')
        period_count = analysis.get('period_grades_count', 0)
        total_count = analysis.get('total_grades_count', 0)
        activity_pluses = analysis.get('activity_pluses', 0)
        activity_minuses = analysis.get('activity_minuses', 0)
        unprepared_count = analysis.get('unprepared_count', 0)

        overall_avg_str = f"{overall_avg:.2f}" if overall_avg is not None else "—"
        period_avg_str = f"{period_avg:.2f}" if period_avg is not None else "—"

        honor_badge = ""
        if overall_avg is not None and overall_avg >= 4.75:
            honor_badge = '<div style="margin-top: 4px; font-size: 11px; background-color: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; display: inline-block; font-weight: bold;">🏅 Świadectwo z wyróżnieniem</div>'

        # Sekcja Sukcesy
        strengths_html = ""
        if analysis.get('insights_strengths'):
            items = "".join([f"<li style='margin-bottom: 6px;'>{s}</li>" for s in analysis['insights_strengths']])
            strengths_html = f"""
            <div style="background-color: #ecfdf5; border-left: 4px solid #10b981; border-radius: 6px; padding: 14px 18px; margin-bottom: 18px;">
                <h4 style="margin: 0 0 8px 0; color: #065f46; font-size: 15px;">🌟 Sukcesy i mocne strony</h4>
                <ul style="margin: 0; padding-left: 20px; color: #047857; font-size: 14px;">
                    {items}
                </ul>
            </div>
            """

        # Sekcja Ostrzeżenia
        warnings_html = ""
        if analysis.get('insights_warnings'):
            items = "".join([f"<li style='margin-bottom: 6px;'>{w}</li>" for w in analysis['insights_warnings']])
            warnings_html = f"""
            <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 14px 18px; margin-bottom: 18px;">
                <h4 style="margin: 0 0 8px 0; color: #92400e; font-size: 15px;">⚠️ Uwagi i obszary do poprawy</h4>
                <ul style="margin: 0; padding-left: 20px; color: #b45309; font-size: 14px;">
                    {items}
                </ul>
            </div>
            """

        # Karta Symulatora Czerwonego Paska
        honor_roll = analysis.get('honor_roll', {})
        honor_roll_html = ""
        if honor_roll.get('qualified'):
            honor_roll_html = f"""
            <div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; width: 100%; box-sizing: border-box;">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%;">
                    <tr>
                        <td width="36" valign="middle" style="font-size: 28px; padding-right: 12px;">🏅</td>
                        <td valign="middle">
                            <h4 style="margin: 0; color: #92400e; font-size: 15px; font-weight: bold;">Kwalifikacja do świadectwa z wyróżnieniem (czerwony pasek)!</h4>
                            <p style="margin: 4px 0 0 0; color: #78350f; font-size: 13px;">{html.escape(honor_roll.get('message', ''))}</p>
                        </td>
                    </tr>
                </table>
            </div>
            """
        elif honor_roll.get('current_avg') is not None and honor_roll.get('current_avg') > 0:
            cur_avg = honor_roll.get('current_avg', 0.0)
            gap = honor_roll.get('gap', 0.0)
            opps = honor_roll.get('key_opportunities', [])
            opps_html = ""
            if opps:
                items = "".join([f"<li><strong>{html.escape(o['subject'])}</strong>: aktualnie {o['current_avg']:.2f} (brakuje {o['dist']:.2f} do oceny {o['target_grade']})</li>" for o in opps])
                opps_html = f"""
                <div style="margin-top: 10px; font-size: 12px; color: #1e3a8a; border-top: 1px dashed #bbf7d0; padding-top: 8px;">
                    <strong>Najszybsza droga do paska (kluczowe przedmioty o najmniejszej stracie):</strong>
                    <ul style="margin: 4px 0 0 0; padding-left: 20px;">{items}</ul>
                </div>
                """
            pct = min(100, max(0, int(((cur_avg - 1.0) / (4.75 - 1.0)) * 100)))
            honor_roll_html = f"""
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; width: 100%; box-sizing: border-box;">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%;">
                    <tr>
                        <td valign="top">
                            <h4 style="margin: 0; color: #166534; font-size: 15px;">🎯 Droga do świadectwa z wyróżnieniem (Czerwony Pasek)</h4>
                            <p style="margin: 4px 0 0 0; color: #15803d; font-size: 13px;">
                                Aktualna średnia: <strong>{cur_avg:.2f}</strong> | Cel: <strong>4.75</strong> (brakuje <strong>{gap:.2f}</strong> pkt)
                            </p>
                        </td>
                        <td align="right" valign="top" style="text-align: right; white-space: nowrap; padding-left: 8px;">
                            <span style="font-size: 13px; font-weight: bold; color: #166534; background-color: #dcfce7; padding: 3px 8px; border-radius: 6px;">{pct}% celu</span>
                        </td>
                    </tr>
                </table>
                <div style="background-color: #dcfce7; border-radius: 10px; height: 10px; width: 100%; margin-top: 10px; overflow: hidden;">
                    <div style="background-color: #16a34a; width: {pct}%; height: 100%; border-radius: 10px;"></div>
                </div>
                {opps_html}
            </div>
            """

        # Karta Na granicy oceny (Szanse i Zagrożenia)
        borderline_opps = analysis.get('borderline_opportunities', [])
        borderline_risks = analysis.get('borderline_risks', [])
        borderline_opp_map = {o['subject']: o for o in borderline_opps}
        borderline_risk_map = {r['subject']: r for r in borderline_risks}

        borderline_html = ""
        if borderline_opps or borderline_risks:
            opps_box = ""
            if borderline_opps:
                items = "".join([f"<li style='margin-bottom: 6px;'><strong>{html.escape(o['subject'])}</strong>: {html.escape(o['advice'])}</li>" for o in borderline_opps])
                opps_box = f"""
                <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; width: 100%; box-sizing: border-box;">
                    <h4 style="margin: 0 0 6px 0; color: #15803d; font-size: 13px;">🎯 Szanse na wyższą ocenę (na wyciągnięcie ręki)</h4>
                    <ul style="margin: 0; padding-left: 18px; font-size: 12px; color: #166534; line-height: 1.45;">
                        {items}
                    </ul>
                </div>
                """
            risks_box = ""
            if borderline_risks:
                items = "".join([f"<li style='margin-bottom: 6px;'><strong>{html.escape(r['subject'])}</strong>: {html.escape(r['warning'])}</li>" for r in borderline_risks])
                risks_box = f"""
                <div style="background-color: #fff7ed; border: 1px solid #fdba74; border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; width: 100%; box-sizing: border-box;">
                    <h4 style="margin: 0 0 6px 0; color: #c2410c; font-size: 13px;">⚖️ Ryzyko obniżenia oceny (mały margines bezpieczeństwa)</h4>
                    <ul style="margin: 0; padding-left: 18px; font-size: 12px; color: #9a3412; line-height: 1.45;">
                        {items}
                    </ul>
                </div>
                """
            borderline_html = f"""
            <div style="margin-bottom: 16px;">
                <h3 style="color: #1f2937; margin: 0 0 10px 0; font-size: 15px; border-bottom: 2px solid #6366f1; padding-bottom: 5px;">
                    🎯 Analiza progów ocen (Kalkulator szans i zagrożeń)
                </h3>
                {opps_box}
                {risks_box}
            </div>
            """

        # Karta Styl nauki i wpływ wag
        learning_style = analysis.get('learning_style', {})
        weight_impact = analysis.get('weight_impact', {})
        stable_subjs = analysis.get('stable_subjects', [])
        volatile_subjs = analysis.get('volatile_subjects', [])

        ls_html = ""
        if learning_style.get('exams_avg') is not None or weight_impact.get('arithmetic_avg') is not None:
            ex_avg = f"{learning_style['exams_avg']:.2f}" if learning_style.get('exams_avg') is not None else "—"
            ex_cnt = learning_style.get('exams_count', 0)
            da_avg = f"{learning_style['daily_avg']:.2f}" if learning_style.get('daily_avg') is not None else "—"
            da_cnt = learning_style.get('daily_count', 0)
            diag = html.escape(learning_style.get('diagnosis', ''))

            wi_desc = html.escape(weight_impact.get('description', ''))
            st_text = ""
            if stable_subjs:
                st_names = ", ".join([html.escape(s['subject']) for s in stable_subjs[:3]])
                st_text = f"<div style='margin-top: 6px;'><strong>Stabilne oceny:</strong> {st_names}</div>"
            vol_text = ""
            if volatile_subjs:
                vol_names = ", ".join([f"{html.escape(v['subject'])} ({v['min']}–{v['max']})" for v in volatile_subjs[:2]])
                vol_text = f"<div style='margin-top: 6px; color: #b45309;'><strong>Duże wahania (sinusoida):</strong> {vol_names}</div>"

            ls_html = f"""
            <div style="margin-bottom: 16px;">
                <h3 style="color: #1f2937; margin: 0 0 10px 0; font-size: 15px; border-bottom: 2px solid #8b5cf6; padding-bottom: 5px;">
                    🔍 Styl nauki i wpływ wag ocen
                </h3>
                <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; width: 100%; box-sizing: border-box;">
                    <h4 style="margin: 0 0 8px 0; color: #334155; font-size: 13px;">Sprawdziany vs Bieżąca praca</h4>
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%; text-align: center; margin-bottom: 8px;">
                        <tr>
                            <td width="50%" style="width: 50%; border-right: 1px solid #e2e8f0; padding-right: 6px;">
                                <div style="font-size: 11px; color: #64748b;">SPRAWDZIANY (waga &ge; 2)</div>
                                <div style="font-size: 20px; font-weight: bold; color: #1e3a8a;">{ex_avg}</div>
                                <div style="font-size: 10px; color: #64748b;">{ex_cnt} ocen</div>
                            </td>
                            <td width="50%" style="width: 50%; padding-left: 6px;">
                                <div style="font-size: 11px; color: #64748b;">PRACA BIEŻĄCA (waga 1)</div>
                                <div style="font-size: 20px; font-weight: bold; color: #059669;">{da_avg}</div>
                                <div style="font-size: 10px; color: #64748b;">{da_cnt} ocen</div>
                            </td>
                        </tr>
                    </table>
                    <div style="font-size: 12px; color: #475569; line-height: 1.4; border-top: 1px solid #e2e8f0; padding-top: 8px;">
                        {diag}
                    </div>
                </div>
                <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 14px; width: 100%; box-sizing: border-box;">
                    <h4 style="margin: 0 0 6px 0; color: #334155; font-size: 13px;">Wpływ wag i stabilność wyników</h4>
                    <div style="font-size: 12px; color: #475569; line-height: 1.4;">
                        <div><strong>Efekt wagowy:</strong> {wi_desc}</div>
                        {st_text}
                        {vol_text}
                    </div>
                </div>
            </div>
            """

        # Karta Ciche przedmioty
        dormant_subjs = analysis.get('dormant_subjects', [])
        dormant_html = ""
        if dormant_subjs:
            d_items = "".join([f"<li><strong>{html.escape(d['subject'])}</strong>: ostatnia ocena {d['last_date_str']} ({d['days_ago']} dni temu)</li>" for d in dormant_subjs if d['days_ago']])
            if d_items:
                dormant_html = f"""
                <div style="background-color: #fefce8; border: 1px solid #fef08a; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; width: 100%; box-sizing: border-box;">
                    <h4 style="margin: 0 0 6px 0; color: #854d0e; font-size: 13px;">⏱️ Ciche przedmioty (brak ocen od ponad 30 dni)</h4>
                    <ul style="margin: 0; padding-left: 18px; font-size: 12px; color: #713f12;">
                        {d_items}
                    </ul>
                </div>
                """

        # Karty ocen wg przedmiotów
        subjects_cards = ""
        for s in analysis.get('subjects', []):
            subj_raw_name = s.get('subject', '')
            subj_name = html.escape(subj_raw_name)
            subj_overall = f"{s['overall_avg']:.2f}" if s.get('overall_avg') is not None else "—"
            subj_period = f"{s['period_avg']:.2f}" if s.get('period_avg') is not None else "—"
            trend_lbl = html.escape(s.get('trend_label', '—'))
            predicted = html.escape(s.get('predicted_grade', '—'))

            trend_color = "#4b5563"
            if s.get('trend') == 'up':
                trend_color = "#059669"
            elif s.get('trend') == 'down':
                trend_color = "#dc2626"

            period_badges = " ".join([cls._format_grade_badge(g.get('grade', '')) for g in s.get('period_grades', [])])
            if not period_badges:
                period_badges = "<span style='color: #9ca3af; font-size: 12px;'>brak</span>"

            all_badges = " ".join([cls._format_grade_badge(g.get('grade', '')) for g in s.get('all_grades', [])])
            if not all_badges:
                all_badges = "<span style='color: #9ca3af; font-size: 12px;'>brak</span>"

            # Badże szans / ryzyka w nagłówku przedmiotu
            border_note = ""
            if subj_raw_name in borderline_opp_map:
                gap_val = borderline_opp_map[subj_raw_name]['gap']
                border_note = f'<span style="display: inline-block; font-size: 11px; background-color: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 1px 5px; border-radius: 4px; font-weight: bold; margin-left: 4px;">🎯 +{gap_val:.2f} do wyższej</span>'
            elif subj_raw_name in borderline_risk_map:
                m_val = borderline_risk_map[subj_raw_name]['margin']
                border_note = f'<span style="display: inline-block; font-size: 11px; background-color: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; padding: 1px 5px; border-radius: 4px; font-weight: bold; margin-left: 4px;">⚠️ margines {m_val:.2f}</span>'

            subjects_cards += f"""
            <div style="border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 10px; background-color: #ffffff; width: 100%; box-sizing: border-box; overflow: hidden;">
                <div style="background-color: #f8fafc; padding: 10px 12px; border-bottom: 1px solid #e2e8f0;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%;">
                        <tr>
                            <td valign="top" style="padding-bottom: 4px;">
                                <span style="font-size: 15px; font-weight: bold; color: #1e293b;">{subj_name}</span>
                                <span style="display: inline-block; font-size: 11px; background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 1px 5px; border-radius: 4px; font-weight: bold; margin-left: 4px;">Prognoza: {predicted}</span>
                                {border_note}
                            </td>
                        </tr>
                        <tr>
                            <td valign="top" style="font-size: 13px; color: #334155;">
                                Śr. ogólna: <strong style="font-size: 15px; color: #1e3a8a;">{subj_overall}</strong>
                                <span style="color: {trend_color}; font-weight: bold; margin-left: 3px;">{trend_lbl}</span>
                                <span style="color: #64748b; font-size: 12px; margin-left: 6px;">(okres: <strong>{subj_period}</strong>)</span>
                            </td>
                        </tr>
                    </table>
                </div>
                <div style="padding: 10px 12px; font-size: 13px;">
                    <div style="margin-bottom: 6px;">
                        <span style="font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;">Oceny w okresie:</span>
                        <div style="margin-top: 3px;">{period_badges}</div>
                    </div>
                    <div>
                        <span style="font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;">Wszystkie oceny:</span>
                        <div style="margin-top: 3px;">{all_badges}</div>
                    </div>
                </div>
            </div>
            """

        # Szczegółowa lista ocen z okresu
        period_details_html = ""
        if analysis.get('period_grades'):
            p_cards = ""
            for g in analysis['period_grades']:
                s_name = html.escape(g.get('subject', ''))
                badge = cls._format_grade_badge(g.get('grade', ''))
                weight = html.escape(str(g.get('weight') or '-'))
                cat = html.escape(str(g.get('category') or '-'))
                date_str = html.escape(str(g.get('date') or '-'))
                teacher = html.escape(str(g.get('teacher') or '-'))
                comm = html.escape(str(g.get('comment') or '-'))

                meta_parts = []
                if teacher and teacher != '-':
                    meta_parts.append(f"<span>👤 <strong>Nauczyciel:</strong> {teacher}</span>")
                if comm and comm != '-':
                    meta_parts.append(f"<span>💬 <strong>Komentarz:</strong> {comm}</span>")

                meta_details = ""
                if meta_parts:
                    meta_details = f"""
                    <div style="font-size: 12px; color: #64748b; margin-top: 6px; padding-top: 6px; border-top: 1px dashed #f1f5f9;">
                        {" &nbsp;|&nbsp; ".join(meta_parts)}
                    </div>
                    """

                p_cards += f"""
                <div style="border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; background-color: #ffffff; width: 100%; box-sizing: border-box;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%;">
                        <tr>
                            <td valign="top" style="padding-bottom: 2px;">
                                <span style="font-weight: bold; font-size: 14px; color: #1e293b;">{s_name}</span>
                                {badge}
                                <span style="display: inline-block; font-size: 11px; background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; padding: 1px 5px; border-radius: 4px; font-weight: bold; margin-left: 3px;">waga {weight}</span>
                                <span style="font-size: 12px; color: #475569; margin-left: 4px;">• {cat}</span>
                            </td>
                            <td align="right" valign="top" style="text-align: right; font-size: 12px; color: #64748b; white-space: nowrap; padding-left: 8px;">
                                🗓️ {date_str}
                            </td>
                        </tr>
                    </table>
                    {meta_details}
                </div>
                """

            period_details_html = f"""
            <div style="margin-top: 20px;">
                <h3 style="color: #1f2937; margin: 0 0 10px 0; font-size: 16px; border-bottom: 2px solid #3b82f6; padding-bottom: 6px;">
                    📝 Oceny zarejestrowane w analizowanym okresie ({len(analysis['period_grades'])})
                </h3>
                {p_cards}
            </div>
            """

        # Histogram ocen (rozkład)
        dist_overall = analysis.get('distribution_overall', {})
        dist_period = analysis.get('distribution_period', {})
        hist_cells = ""
        for grade_num in ['6', '5', '4', '3', '2', '1']:
            cnt_all = dist_overall.get(grade_num, 0)
            cnt_p = dist_period.get(grade_num, 0)
            badge = cls._format_grade_badge(grade_num)
            p_text = f"+{cnt_p} w okresie" if cnt_p > 0 else "0 w okresie"
            hist_cells += f"""
            <td width="16%" align="center" valign="top" style="width: 16.6%; background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px 2px; text-align: center;">
                <div style="margin-bottom: 2px;">{badge}</div>
                <div style="font-size: 16px; font-weight: bold; color: #1f2937;">{cnt_all}</div>
                <div style="font-size: 10px; color: #6b7280; line-height: 1.1;">{p_text}</div>
            </td>
            """

        # Przewodnik rodzica (Legenda jak rozumieć wskaźniki) - 2 porady na wiersz
        legend = analysis.get('legend', {})
        legend_html = f"""
        <div style="margin-top: 25px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; box-sizing: border-box; width: 100%;">
            <h3 style="margin: 0 0 10px 0; color: #1e3a8a; font-size: 15px;">
                📖 Przewodnik rodzica: Jak rozumieć wskaźniki w raporcie?
            </h3>
            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%; border-collapse: separate; border-spacing: 6px;">
                <tr>
                    <td width="50%" valign="top" style="width: 50%; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; color: #475569; line-height: 1.45;">
                        <strong style="color: #1e293b;">🎯 Skala i progi ocen:</strong><br>
                        {html.escape(legend.get('thresholds', ''))}
                    </td>
                    <td width="50%" valign="top" style="width: 50%; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; color: #475569; line-height: 1.45;">
                        <strong style="color: #1e293b;">📈 Wskaźniki trendu (↗, ↘, ➡, ✨):</strong><br>
                        {html.escape(legend.get('trends', ''))}
                    </td>
                </tr>
                <tr>
                    <td width="50%" valign="top" style="width: 50%; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; color: #475569; line-height: 1.45;">
                        <strong style="color: #1e293b;">⚖️ Średnia ważona a wagi ocen:</strong><br>
                        {html.escape(legend.get('weight_impact', ''))}
                    </td>
                    <td width="50%" valign="top" style="width: 50%; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; color: #475569; line-height: 1.45;">
                        <strong style="color: #1e293b;">🎯 Analiza na granicy ocen:</strong><br>
                        {html.escape(legend.get('borderline', ''))}
                    </td>
                </tr>
                <tr>
                    <td width="50%" valign="top" style="width: 50%; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; color: #475569; line-height: 1.45;">
                        <strong style="color: #1e293b;">🔍 Styl nauki (sprawdziany / kartkówki):</strong><br>
                        {html.escape(legend.get('learning_style', ''))}
                    </td>
                    <td width="50%" valign="top" style="width: 50%; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; font-size: 12px; color: #475569; line-height: 1.45;">
                        <strong style="color: #1e293b;">🎢 Stabilność ocen vs Sinusoida:</strong><br>
                        {html.escape(legend.get('stability', ''))}
                    </td>
                </tr>
            </table>
        </div>
        """

        contents = f"""
        <div style="width: 100%; max-width: 650px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937; line-height: 1.5; background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; box-sizing: border-box; overflow: hidden;">
            <!-- Nagłówek -->
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: #ffffff; padding: 16px;">
                <h1 style="margin: 0; font-size: 19px; font-weight: 700; color: #ffffff;">📊 Raport postępów ucznia</h1>
                <p style="margin: 4px 0 0 0; font-size: 14px; opacity: 0.95; color: #ffffff;">
                    <strong>{name}</strong> (konto Librus: <code>{login}</code>)
                </p>
                <div style="margin-top: 6px; font-size: 12px; opacity: 0.9; color: #ffffff;">
                    🗓️ Okres: <strong>{p_start}</strong> – <strong>{p_end}</strong>
                </div>
            </div>

            <div style="padding: 14px; box-sizing: border-box;">
                <!-- Kafelki KPI (Tabela 2x2 z szerokościami 50%) -->
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%; margin-bottom: 16px; border-collapse: separate; border-spacing: 6px;">
                    <tr>
                        <td width="50%" valign="top" style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 6px; text-align: center;">
                            <div style="font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;">Średnia ogólna</div>
                            <div style="font-size: 24px; font-weight: bold; color: #1e3a8a; margin: 3px 0;">{overall_avg_str}</div>
                            {honor_badge}
                        </td>
                        <td width="50%" valign="top" style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 6px; text-align: center;">
                            <div style="font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;">Średnia w okresie</div>
                            <div style="font-size: 24px; font-weight: bold; color: #059669; margin: 3px 0;">{period_avg_str}</div>
                            <div style="font-size: 10px; color: #64748b;">{p_start} – {p_end}</div>
                        </td>
                    </tr>
                    <tr>
                        <td width="50%" valign="top" style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 6px; text-align: center;">
                            <div style="font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;">Oceny w okresie</div>
                            <div style="font-size: 24px; font-weight: bold; color: #2563eb; margin: 3px 0;">{period_count}</div>
                            <div style="font-size: 10px; color: #64748b;">z {total_count} zarejestrowanych</div>
                        </td>
                        <td width="50%" valign="top" style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 6px; text-align: center;">
                            <div style="font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase;">Aktywność / Uwagi</div>
                            <div style="font-size: 17px; font-weight: bold; color: #334155; margin: 4px 0;">
                                +{activity_pluses} / -{activity_minuses}
                            </div>
                            <div style="font-size: 11px; color: #ef4444; font-weight: bold;">np/bz: {unprepared_count}</div>
                        </td>
                    </tr>
                </table>

                <!-- Rekomendacje i wnioski -->
                {strengths_html}
                {warnings_html}

                <!-- Czerwony pasek i analiza progów -->
                {honor_roll_html}
                {borderline_html}

                <!-- Styl nauki i wpływ wag -->
                {ls_html}

                <!-- Ciche przedmioty -->
                {dormant_html}

                <!-- Karty ocen wg przedmiotów -->
                <div style="margin-top: 20px;">
                    <h3 style="color: #1f2937; margin: 0 0 10px 0; font-size: 16px; border-bottom: 2px solid #1e3a8a; padding-bottom: 6px;">
                        📚 Zestawienie ocen według przedmiotów
                    </h3>
                    {subjects_cards}
                </div>

                <!-- Szczegóły nowych ocen -->
                {period_details_html}

                <!-- Rozkład ocen -->
                <div style="margin-top: 20px;">
                    <h3 style="color: #1f2937; margin: 0 0 10px 0; font-size: 16px; border-bottom: 2px solid #64748b; padding-bottom: 6px;">
                        📈 Rozkład ocen (cały okres vs ostatni raport)
                    </h3>
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="width: 100%; border-collapse: separate; border-spacing: 3px;">
                        <tr>
                            {hist_cells}
                        </tr>
                    </table>
                </div>

                <!-- Przewodnik rodzica (Legenda) -->
                {legend_html}

                <!-- Stopka -->
                <div style="margin-top: 25px; padding-top: 15px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; text-align: center;">
                    Raport postępów wygenerowany automatycznie przez <strong>Librus2mail</strong>. Wartości średnich obliczone na podstawie wag przypisanych w Librus Synergia.
                </div>
            </div>
        </div>
        """
        return contents

    def send_progress_report(self, user_config: dict, analysis: dict) -> bool:
        pass

    @classmethod
    def _get_error_diagnostics(cls, error: Exception) -> tuple[str, str, str]:
        err_name = type(error).__name__
        err_str = str(error)
        err_lower = err_str.lower()

        if err_name == 'NotLogged' or 'brak dostępu' in err_lower or 'sesja' in err_lower or 'nie zalogowany' in err_lower:
            category = "Błąd autoryzacji / sesji Librus"
            diagnosis = "Sesja w portalu Librus Synergia wygasła lub autoryzacja konta nie powiodła się."
            recommendation = (
                "1. Upewnij się, że login i hasło w pliku konfiguracyjnym są poprawne.<br>"
                "2. <strong>Zaloguj się ręcznie przez przeglądarkę na portal.librus.pl</strong> (lub synergia.librus.pl) – "
                "szkoła lub Librus może wymagać zaakceptowania nowego regulaminu, zgody na przetwarzanie danych, zmiany hasła "
                "lub odczytania obowiązkowej wiadomości dyrekcji/ankiety, co blokuje automatyczny dostęp do dziennika.<br>"
                "3. Upewnij się, że konto nie zostało tymczasowo zablokowane z powodu zbyt wielu nieudanych prób logowania."
            )
        elif (
            'connection' in err_name.lower()
            or 'timeout' in err_name.lower()
            or 'ssl' in err_name.lower()
            or 'http' in err_name.lower()
            or 'resolution' in err_lower
            or 'max retries' in err_lower
            or 'failed to establish a new connection' in err_lower
        ):
            category = "Błąd połączenia sieciowego"
            diagnosis = "Nie udało się nawiązać stabilnego połączenia z serwerami Librus (brak połączenia z siecią, timeout lub błąd SSL/DNS)."
            recommendation = (
                "1. Sprawdź połączenie internetowe na serwerze/komputerze uruchamiającym aplikację.<br>"
                "2. Sprawdź w przeglądarce, czy portal https://synergia.librus.pl działa prawidłowo (możliwa przerwa techniczna Librusa).<br>"
                "3. Jeśli problem występuje regularnie, upewnij się, że zapora sieciowa (firewall) nie blokuje zapytań HTTPS."
            )
        elif err_name in ('AttributeError', 'TypeError', 'KeyError', 'IndexError') or 'parse' in err_lower or 'soup' in err_lower:
            category = "Błąd parsowania danych (zmiana struktury HTML)"
            diagnosis = "Dane ze strony Librusa zostały pobrane, lecz skrypt nie był w stanie wyodrębnić z nich informacji. Prawdopodobnie Librus zaktualizował strukturę HTML dziennika."
            recommendation = (
                "1. Sprawdź szczegółowy log w pliku <code>librus.log</code>.<br>"
                "2. Zaloguj się przez przeglądarkę i sprawdź, czy w dzienniku nie pojawił się niestandardowy komunikat lub okno modalne zastępujące widok danych.<br>"
                "3. Jeśli struktura strony uległa trwałej zmianie, konieczna może być aktualizacja selektorów w kodzie."
            )
        else:
            category = f"Błąd wykonania ({err_name})"
            diagnosis = f"Wystąpił nieoczekiwany błąd podczas pracy aplikacji: {err_str}"
            recommendation = "Sprawdź plik <code>librus.log</code> oraz poniższe szczegóły techniczne w celu zdiagnozowania problemu."

        return category, diagnosis, recommendation

    @staticmethod
    def _create_error_title(user_config: dict, error: Exception, step_name: str = "") -> str:
        step_labels = {
            'inicjalizacja': 'Inicjalizacja',
            'logowanie': 'Logowanie',
            'wiadomości': 'Pobieranie wiadomości',
            'ogłoszenia': 'Pobieranie ogłoszeń',
            'oceny': 'Pobieranie ocen'
        }
        step_desc = step_labels.get(step_name, step_name or "Komunikacja")
        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        login = user_config.get('librus_login', '')
        return f"[ALERT] {name} - Librus: Błąd ({step_desc}) [konto {login}]"

    @classmethod
    def create_mail_content_for_error(
        cls,
        user_config: dict,
        error: Exception,
        step_name: str = "",
        details: str = None,
        cooldown_s: int = 3600
    ) -> str:
        step_labels = {
            'inicjalizacja': 'Inicjalizacja parsera',
            'logowanie': 'Logowanie do portalu Synergia',
            'wiadomości': 'Pobieranie wiadomości',
            'ogłoszenia': 'Pobieranie ogłoszeń',
            'oceny': 'Pobieranie ocen'
        }
        step_label = step_labels.get(step_name, step_name or "Komunikacja z portalem")
        category, diagnosis, recommendation = cls._get_error_diagnostics(error)

        name = html.escape(str(user_config.get('librus_login_name') or user_config.get('librus_login', '')))
        login = html.escape(str(user_config.get('librus_login', '')))
        error_msg = html.escape(f"{type(error).__name__}: {str(error)}")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cooldown_min = max(1, cooldown_s // 60)

        details_html = ""
        if details:
            escaped_details = html.escape(str(details))
            details_html = f"""
            <details style="margin: 15px 0;">
                <summary style="cursor: pointer; color: #7f8c8d; font-size: 13px; font-weight: bold;">Szczegóły techniczne (traceback)</summary>
                <pre style="background-color: #2c3e50; color: #ecf0f1; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; margin-top: 8px;">{escaped_details}</pre>
            </details>
            """

        contents = f"""
        <div style="font-family: Arial, sans-serif; color: #333333; max-width: 700px; line-height: 1.5;">
            <div style="background-color: #e74c3c; color: #ffffff; padding: 15px 20px; border-radius: 6px 6px 0 0;">
                <h2 style="margin: 0; font-size: 18px;">⚠️ Librus2mail: Błąd pobierania danych</h2>
            </div>
            
            <div style="border: 1px solid #e0e0e0; border-top: none; padding: 20px; border-radius: 0 0 6px 6px; background-color: #ffffff;">
                <p style="font-size: 14px; margin-top: 0;">
                    Podczas cyklicznego sprawdzania dziennika Librus dla konta <strong>{name}</strong> 
                    (login: <code>{login}</code>) wystąpił błąd uniemożliwiający pobranie aktualnych danych.
                </p>

                <table style="width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 14px;">
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold; width: 28%;">Etap:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">{step_label}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Kategoria błędu:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6; color: #c0392b; font-weight: bold;">{category}</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Komunikat:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;"><code>{error_msg}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Data wystąpienia:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">{current_time}</td>
                    </tr>
                </table>

                <div style="background-color: #e8f4f8; border-left: 4px solid #3498db; padding: 12px 16px; margin: 20px 0; border-radius: 4px;">
                    <h4 style="margin: 0 0 8px 0; color: #2980b9;">🔍 Diagnoza</h4>
                    <p style="margin: 0; font-size: 14px;">{diagnosis}</p>
                </div>

                <div style="background-color: #fef9e7; border-left: 4px solid #f39c12; padding: 12px 16px; margin: 20px 0; border-radius: 4px;">
                    <h4 style="margin: 0 0 8px 0; color: #d68910;">💡 Zalecane działanie</h4>
                    <div style="margin: 0; font-size: 14px;">{recommendation}</div>
                </div>

                {details_html}

                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #7f8c8d; margin-bottom: 0;">
                    ℹ️ <em>Powiadomienia o kolejnych wystąpieniach tego samego błędu są wyciszane na {cooldown_min} minut, aby nie zaśmiecać skrzynki. Gdy błąd ustąpi, stan zostanie automatycznie zresetowany.</em>
                </p>
            </div>
        </div>
        """
        return contents

    @staticmethod
    def should_send_error_notification(storage, user_login: str, error_str: str, cooldown_s: int = 3600) -> bool:
        if not storage:
            return True
        last_err = storage.get_last_error(str(user_login))
        if not last_err:
            return True
        if cooldown_s <= 0:
            return True
        last_timestamp = last_err.get('timestamp', 0)
        last_msg = last_err.get('error', '')
        if error_str != last_msg:
            return True
        now = datetime.now().timestamp()
        if now - last_timestamp >= cooldown_s:
            return True
        return False

    def send_error_notification(
        self,
        user_config: dict,
        error: Exception,
        step_name: str = "",
        details: str = None,
        storage=None,
        cooldown_s: int = 3600
    ) -> bool:
        pass


