# Bauplan & Betriebsordnung eines Hausverwaltungs-OS

## Systemverfassung für ein KI-natives Verwaltungssystem

Dieses Dokument ist keine Produktbeschreibung und kein Kundenversprechen.

Es ist die **Betriebsverfassung des Systems**.

Es definiert, welche Tatsachen das System als wahr behandeln darf, welche Entscheidungen es vorbereiten darf, welche Handlungen es selbst ausführen darf, wann ein Mensch tatsächlich entscheiden muss und welche Grenzen weder Modell, Workflow noch Administrator stillschweigend umgehen dürfen.

Das Ziel ist ausdrücklich nicht:

**„KI macht alles.“**

Das Ziel ist:

**„Das System erledigt alles, was innerhalb eines expliziten Mandats sicher, reproduzierbar und nachvollziehbar erledigt werden kann – und eskaliert alles andere mit maximal vorbereitetem Entscheidungskontext.“**

Diese Unterscheidung ist fundamental.

Ein menschlicher Klick am Ende eines vollständig automatisierten Prozesses ist keine belastbare Sicherheitsarchitektur. Ebenso wenig ist eine pauschale Freigabepflicht für jede relevante Aktion sinnvoll. Sie erzeugt Freigabemüdigkeit, verlangsamt den Betrieb und führt langfristig dazu, dass Menschen Entscheidungen lediglich bestätigen, statt sie tatsächlich zu prüfen.

Deshalb basiert HVOS nicht auf der simplen Trennung zwischen „KI“ und „Mensch“, sondern auf **Entscheidungsrechten, Mandaten und Wirkungsklassen**.

---

# 01 · Kernthese

## Nicht: Die KI arbeitet, der Mensch entscheidet.

Die präzisere Regel lautet:

> **Das System darf innerhalb eines nachweisbaren Mandats autonom handeln. Außerhalb dieses Mandats darf es vorbereiten, simulieren und empfehlen – aber keine externe Wirkung erzeugen.**

Die verantwortliche menschliche oder organisatorische Rolle bleibt dabei bestimmbar.

Verantwortung darf niemals dadurch simuliert werden, dass ein Mensch lediglich einen von der Maschine vorgefertigten Vorgang „freigibt“.

Eine Freigabe ist nur dann ein echtes Kontrollinstrument, wenn die freigebende Person mindestens erkennen kann:

**Was wird getan? Warum? Auf welcher Datengrundlage? Aufgrund welcher Befugnis? Mit welcher finanziellen oder rechtlichen Wirkung? Was hat sich gegenüber dem Ausgangszustand verändert? Kann die Handlung rückgängig gemacht werden?**

Fehlt eine dieser Informationen, ist das Freigabe-Gate unvollständig.

Die zentrale Systemfrage lautet deshalb bei jeder Aktion nicht:

**„Darf KI das?“**

Sondern:

**„Ist diese konkrete Aktion in diesem konkreten Zustand durch dieses konkrete Mandat gedeckt?“**

Das ist eine wesentlich stärkere Architektur.

---

# 02 · Schichtenmodell

Die Architektur sollte nicht entlang einzelner Technologien gedacht werden, sondern entlang unterschiedlicher Arten von Wahrheit und Verantwortung.

| Ebene | Aufgabe | Darf generativ sein? |
|---|---|---:|
| **1 · System of Record** | Verträge, Personen, Objekte, Konten, Buchungen, Beschlüsse, Dokumente | Nein |
| **2 · Domain Engine** | Fristen, Umlagen, Forderungen, Salden, Abrechnungslogik | Nein |
| **3 · Authority & Policy Engine** | Mandate, Rollen, Schwellenwerte, Freigaben, Verbote | Nein |
| **4 · Action Runtime** | Typisierte, idempotente Ausführung realer Aktionen | Nein |
| **5 · Intelligence Layer** | Extraktion, Klassifikation, Entwürfe, Erklärungen, Planung | Ja |
| **6 · Decision Experience** | Warteschlange, Ausnahmen, Freigaben, Simulationen | Teilweise |

**Audit, Herkunft, Sicherheit und Observability sind keine siebte Schicht.**

Sie sind eine **Querschnittsebene**, die jede Schicht durchdringt.

Das verhindert einen häufigen Architekturfehler: Audit darf nicht erst beim „KI-Teil“ beginnen. Auch eine deterministisch berechnete Nachforderung muss rekonstruierbar sein.

Ebenso wichtig:

Die Intelligence Layer darf niemals direkt Seiteneffekte erzeugen.

Ein LLM darf beispielsweise zu dem Ergebnis kommen:

> „Diese Rechnung scheint freigabefähig.“

Es darf aber nicht daraus unmittelbar einen Banktransfer erzeugen.

Zwischen Interpretation und Wirkung liegt immer die Authority & Policy Engine.

---

# 03 · Datenmodell

## Das bisherige lineare Modell ist zu schwach.

`Objekt → Einheit → Person → Konto → Vorgang → Dokument → Aktion`

ist als mentale Einstiegshilfe brauchbar, aber nicht als belastbares Domain-Modell.

Hausverwaltung ist keine Hierarchie.

Sie ist ein **zeitabhängiger Graph aus Rechtsträgern, Rollen, Verträgen, Beschlüssen, Vermögen und Verpflichtungen**.

Eine Person ist beispielsweise nicht einfach „einer Einheit zugeordnet“.

Dieselbe Person kann gleichzeitig Eigentümer einer Einheit, ehemaliger Eigentümer einer anderen Einheit, Mieter einer dritten Einheit, Beiratsmitglied und Rechnungsempfänger sein.

Jede dieser Beziehungen kann einen anderen Gültigkeitszeitraum besitzen.

Deshalb müssen Beziehungen selbst zu versionierten Entitäten werden.

Der Kern sollte mindestens folgende Konzepte unterscheiden:

**Legal Entity, Property, Unit, Party, Role, Mandate, Ownership, Tenancy, Contract, Resolution, Bank Account, Ledger Account, Transaction, Invoice, Cost Item, Allocation Rule, Meter, Meter Reading, Claim, Case, Document, Evidence, Communication, Deadline, Action, Approval und Audit Event.**

Entscheidend ist dabei nicht nur der Zustand heute.

HVOS muss beispielsweise beantworten können:

> Wer war am 31.12.2025 Eigentümer?

und gleichzeitig:

> Seit wann wissen wir, dass diese Person am 31.12.2025 Eigentümer war?

Das spricht für ein mindestens temporal versioniertes Datenmodell; bei kritischen Domänen kann bitemporale Modellierung sinnvoll sein.

### Kritische Korrektur zur Kontenlogik

Die bisherige Formulierung **„WEG-Treuhand getrennt“** sollte entfernt werden.

Sie kann technisch falsch interpretiert werden.

Zielzustand ist vielmehr:

> **Gemeinschaftsvermögen muss eindeutig der jeweiligen Gemeinschaft zugeordnet und von Vermögen des Verwalters sowie anderer Mandate getrennt sein. Bankkonten der GdWE müssen auf die Gemeinschaft als Rechtsträger ausgerichtet sein; die Verwaltung erhält Verfügungsberechtigung, nicht wirtschaftliches Eigentum.**

Das Einlagensicherungsgesetz behandelt ausdrücklich Konten auf den Namen einer Gemeinschaft von Wohnungseigentümern; auch die einschlägige Rechtsprechung bzw. Fachliteratur unterscheidet diese von einem auf den Verwalter lautenden Treuhandkonto.

Der zweite nicht verhandelbare Punkt bleibt richtig, muss aber präziser werden:

**Kein Umlageschlüssel ohne Herkunft, Gültigkeitszeitraum und Rechtsgrundlage.**

Ein Schlüssel ist nicht einfach `30/1000`.

Er braucht beispielsweise:

`source = Teilungserklärung`

`effective_from = …`

`scope = Kostenart …`

`superseded_by = Beschluss …`

Denn Kostenverteilungen können sich aus gesetzlichen Regeln, Vereinbarungen oder Beschlüssen ergeben. § 16 WEG erlaubt unter bestimmten Voraussetzungen abweichende Kostenverteilungen durch Beschluss.

---

# 04 · Deterministischer Kern

Auch hier sollte die bisherige Aussage korrigiert werden.

Nicht:

> „Fristen, Umlagen und Heizkosten dürfen niemals LLM sein.“

Sondern:

> **Jede geschäftskritische Berechnung muss reproduzierbar, testbar und versioniert sein.**

Ein Sprachmodell darf durchaus Informationen dafür extrahieren.

Beispiel:

Ein Modell liest einen Mietvertrag und extrahiert:

`abrechnungszeitraum = Kalenderjahr`

`umlagevereinbarung = vorhanden`

`wohnfläche = 82,4 m²`

Diese Werte sind zunächst **Behauptungen des Extraktionssystems**.

Sie werden anschließend normalisiert und validiert.

Erst der deterministische Domain-Kern berechnet daraus einen finanziellen oder rechtlich relevanten Zustand.

Das Muster lautet:

**Dokument → Extraktion → Evidenz → Validierung → strukturierte Tatsache → Regelberechnung → Ergebnis → Erklärung**

Nicht:

**Dokument → LLM → Ergebnis**

Fristen sind ein gutes Beispiel.

§ 556 Abs. 3 BGB legt für Betriebskostenabrechnungen unter anderem die jährliche Abrechnung und grundsätzlich eine Zwölfmonatsfrist nach Ende des Abrechnungszeitraums fest. Das ist deterministisch berechenbar – sobald Abrechnungszeitraum und einschlägige Vertragslage zuverlässig bestimmt sind.

Dasselbe gilt für Heizkosten.

Die HeizkostenV enthält spezifische Regeln für Verbrauchserfassung und Kostenverteilung und sogar Kürzungsrechte bei bestimmten Verstößen. Solche Regeln gehören in versionierte Fachlogik und nicht in einen frei formulierenden Modellprompt.

Jede Berechnung muss deshalb nicht nur einen Wert zurückgeben, sondern mindestens:

**Input-Snapshot + Regelversion + Ergebnis + Ausführungszeitpunkt.**

---

# 05 · Aktionsmodell

## Die wichtigste Änderung des gesamten Berichts

Die 18 Aktionen sind sinnvoll.

Die Einstufung jeder Aktion als dauerhaft

`Auto / Freigabe / Nie automatisch`

ist jedoch zu statisch.

Eine Aktion besitzt nicht intrinsisch eine einzige Risikoklasse.

Beispiel:

**Handwerker beauftragen**

kann sein:

`Auto`  
bei 89 € innerhalb eines freigegebenen Wartungsvertrags.

`Freigabe`  
bei 4.800 € für eine nicht dringende Reparatur.

`Sofort ausführen + nachgelagerte Kontrolle`  
bei einem akuten Wasserschaden.

`Verboten`  
wenn kein Verwaltungsmandat für das Objekt besteht.

Die Klasse entsteht also erst aus Aktion **und Kontext**.

Jede Aktion benötigt deshalb einen technischen **Action Contract** mit mindestens:

`action_type`

`actor`

`legal_entity`

`object_scope`

`inputs`

`preconditions`

`authority_basis`

`financial_impact`

`legal_impact`

`external_effect`

`reversibility`

`required_evidence`

`approval_policy`

`idempotency_key`

`rollback_or_compensation`

`execution_adapter`

`audit_schema`

Aus diesen Eigenschaften berechnet die Policy Engine einen Ausführungszustand:

**ALLOW_AUTO**

**REQUIRE_APPROVAL**

**ESCALATE**

**FORBID**

Damit verschiebt sich eine entscheidende Designentscheidung:

Nicht Entwickler entscheiden einmalig, ob „Mahnung senden“ automatisch ist.

Das System entscheidet anhand einer versionierten Policy, ob **diese Mahnung in diesem Fall** automatisch versendet werden darf.

---

## Das Muster „Entwerfen = Auto, Versenden = Freigabe“

Dieses Muster ist als Default gut, darf aber nicht zum Dogma werden.

Ein vollkommen harmloser, standardisierter Eingangsbeleg oder eine Terminbestätigung muss möglicherweise nicht dauerhaft einen Menschen beschäftigen.

Umgekehrt kann bereits ein **Entwurf** problematisch sein, wenn er auf falschen Rechtsannahmen basiert oder sensible personenbezogene Daten unzulässig verarbeitet.

Die bessere Regel lautet daher:

> **Interne reversible Verarbeitung darf großzügiger automatisiert werden als externe irreversible Wirkung.**

Das ist allgemeiner und stabiler.

---

## „Klage vorbereiten, aber kein Senden-Button“

Auch diese Regel würde ich präzisieren.

„Kein Button“ ist UI-Sicherheit.

HVOS braucht aber **Capability-Sicherheit**.

Es reicht nicht, die Oberfläche zu verstecken.

Die Action Runtime selbst darf ohne einen zulässigen Ausführungskanal keine Aktion wie

`file_court_action`

besitzen.

Die richtige Trennung lautet deshalb beispielsweise:

`prepare_legal_case = allowed`

`generate_case_bundle = allowed`

`send_to_external_counsel = approval_required`

`file_with_court = unsupported_or_external_authority`

Das Verbot sitzt damit in der Capability- und Policy-Ebene – nicht in der Oberfläche.

---

# 06 · Freigabe-Gate

Eine Freigabe darf niemals nur ein Button sein.

Ein Gate ist ein **gebundener Entscheidungsgegenstand**.

Eine gültige Freigabe bezieht sich auf einen konkreten Zustand der Welt.

Ändert sich zwischen Freigabe und Ausführung beispielsweise Betrag, Empfänger, Dokument, Kontoverbindung oder Vertragsgrundlage, erlischt die Freigabe.

Das Approval-Objekt muss deshalb an einen unveränderlichen Action-Snapshot gebunden werden.

Das Gate zeigt nicht primär die vom Modell formulierte Empfehlung.

Es zeigt:

**Wirkung. Quellen. Abweichungen. Risiko. Mandat. Konsequenz.**

Bei finanziellen oder besonders kritischen Aktionen kann zusätzlich ein Vier-Augen-Prinzip erforderlich sein.

Und das System muss verhindern, dass Freigaben durch Gewohnheit wertlos werden.

Dazu gehört beispielsweise:

Automatisierbare Fälle aus der Queue entfernen.

Nur echte Ausnahmen zeigen.

Risikoabhängig Informationen verdichten.

Wiederholte identische Freigaben in neue Policies überführen können.

Die Zielmetrik lautet nicht:

**„Wie viele Freigaben wurden erteilt?“**

Sondern:

**„Wie viele menschliche Entscheidungen waren tatsächlich notwendig?“**

---

# 07 · Audit, Evidenz & Herkunft

**„Herkunft vor Konfidenz“** ist richtig, aber noch nicht stark genug.

Die Regel sollte lauten:

> **Keine relevante Behauptung ohne Evidenz. Keine relevante Handlung ohne rekonstruierbare Entscheidungsgrundlage.**

Konfidenz ist nur Metadatum.

`confidence = 0.98`

macht eine unbelegte Aussage nicht wahr.

Jede entscheidungsrelevante Information braucht deshalb eine Kette:

**Quelle → Extraktion → strukturierte Tatsache → Regel → Entscheidung → Aktion → Ergebnis**

Ein Audit Event sollte mindestens enthalten:

Zeitpunkt, handelnde Identität, Mandat, Aktion, relevante Eingaben, Policy-Version, Regelversion, Evidenzreferenzen, Freigabe, Ausführungsergebnis und Zustandsänderung.

Bei KI-gestützten Schritten zusätzlich Modell- und Systemversion.

Nicht gespeichert werden sollte dagegen wahllos jedes interne Modellartefakt.

Insbesondere ist ein Audit-System kein Ablageort für unbegrenzte Prompts oder interne Gedankengänge.

Gespeichert werden sollte eine **strukturierte, prüfbare Begründung mit Evidenz**, nicht unnötiger Modell-Noise oder personenbezogener Datenballast.

Audit muss außerdem manipulationsresistent sein.

Korrekturen werden nicht durch Überschreiben alter Ereignisse vorgenommen, sondern durch neue Ereignisse.

---

# 08 · Rolle der KI

Die bisherige Aufteilung

**Wahrnehmen · Entwerfen · Erklären · Orchestrieren**

ist gut.

„Orchestrieren“ muss allerdings enger definiert werden.

Orchestrierung bedeutet nicht:

> Das Modell entscheidet selbstständig, welche externen Tools es benutzen darf.

Sondern:

> Das Modell kann einen Plan erzeugen. Jede daraus resultierende Action wird separat durch Policy und Preconditions geprüft.

Die KI darf:

**wahrnehmen**  
Dokumente klassifizieren, Inhalte extrahieren, Zusammenhänge erkennen.

**strukturieren**  
Unstrukturierte Information in Domain-Objekte überführen.

**entwerfen**  
Nachrichten, Beschlussvorlagen, Aufgaben oder Handlungsvorschläge vorbereiten.

**erklären**  
Berechnungen, Regeln, Abweichungen und Entscheidungen verständlich machen.

**planen**  
mehrstufige Bearbeitungswege vorschlagen.

**orchestrieren**  
zulässige Action Contracts anstoßen.

Die KI darf niemals:

sich selbst Berechtigungen geben,

fehlende Rechtsgrundlagen erfinden,

unsichere Daten stillschweigend als Fakten persistieren,

Audit-Ereignisse verändern,

Policy-Gates umgehen,

Geld- oder Rechtswirkung außerhalb eines Mandats erzeugen,

oder fehlende Evidenz durch sprachliche Sicherheit kaschieren.

---

# 09 · Dashboard

## Nicht nur Entscheidungs-Warteschlange.

Die Idee ist richtig, aber ein reines Approval Dashboard wäre zu eng.

Das zentrale Interface von HVOS sollte eine **Exception & Decision Queue** sein.

Der Normalfall soll möglichst unsichtbar funktionieren.

Die Oberfläche konzentriert menschliche Aufmerksamkeit auf vier Dinge:

**Entscheidungen**

**Abweichungen**

**Fristen**

**Störungen**

Ein Nutzer sollte morgens nicht zuerst „Objekte“ öffnen müssen.

Er sollte sehen:

> 3 Entscheidungen benötigen dich.

> 2 Fristen sind gefährdet.

> 1 Zahlung weicht vom erwarteten Muster ab.

> 4 Vorgänge sind blockiert, weil Evidenz fehlt.

> 96 weitere Vorgänge laufen innerhalb der Policy.

Das ist der eigentliche Vorteil eines KI-nativen Betriebssystems.

Nicht mehr Informationen anzeigen.

Sondern **Aufmerksamkeit steuern**.

Gleichzeitig darf das System keine künstliche Dringlichkeit erzeugen.

Jede Priorisierung muss nachvollziehbar sein.

Ein roter Zustand benötigt einen objektiven Grund.

---

# 10 · Rechtlicher Rahmen

Dieser Abschnitt sollte fundamental umgebaut werden.

Keine lose Paragraphensammlung.

HVOS benötigt ein **versioniertes Legal & Policy Registry**.

Ein Rechtssatz wird nicht als Kommentar gespeichert, sondern als strukturierter Systemanker mit:

**Jurisdiktion · Quelle · Gültigkeit · Anwendungsbereich · Trigger · Regel · Ausnahme · Evidenzanforderung · Prüfer · letzte Rechtsprüfung.**

Beispiele:

§ 556 BGB ist unter anderem für die Abrechnung von Betriebskostenvorauszahlungen und die dort geregelten Fristen relevant. § 556a BGB regelt Abrechnungsmaßstäbe.

Die BetrKV unterscheidet Betriebskosten ausdrücklich von Verwaltungs- sowie Instandhaltungs- und Instandsetzungskosten. Diese Trennung muss auch das Kostenmodell von HVOS abbilden.

Für WEG-Verwaltung sind nicht nur § 24 WEG relevant. Besonders wichtig sind auch § 16 zur Kostenverteilung, § 23 zur Beschlussfassung, § 27 zu Aufgaben und Befugnissen des Verwalters und § 28 zu Wirtschaftsplan, Jahresabrechnung und Vermögensbericht.

§ 24 WEG enthält unter anderem Vorgaben zur Einberufung und Beschluss-Sammlung; die reguläre Einberufungsfrist soll mindestens drei Wochen betragen.

Die HeizkostenV benötigt eine eigene Regelgruppe und darf nicht lediglich als weiterer Umlageschlüssel betrachtet werden.

Datenschutz gehört ebenfalls in diesen Abschnitt.

HVOS verarbeitet personenbezogene, finanzielle und potenziell konfliktbehaftete Informationen. Zweckbindung, Datenminimierung und Richtigkeit müssen deshalb bereits im Datenmodell berücksichtigt werden; Datenschutz durch Technikgestaltung und angemessene technische und organisatorische Sicherheitsmaßnahmen sind keine nachträglichen Compliance-Features.

Auch automatisierte Entscheidungen müssen differenziert betrachtet werden. Art. 22 DSGVO betrifft ausschließlich automatisierte Entscheidungen, die rechtliche Wirkung entfalten oder Personen ähnlich erheblich beeinträchtigen. Deshalb reicht auch hier die primitive Regel „Mensch klickt = DSGVO gelöst“ nicht aus.

Der EU AI Act sollte ebenfalls als eigener Compliance-Kontext geführt werden. Ein gewöhnliches Hausverwaltungs-Assistenzsystem ist nicht automatisch ein Hochrisiko-KI-System. Entscheidend ist der konkrete Verwendungszweck. Der AI Act behandelt jedoch unter anderem bestimmte Systeme rund um wesentliche Dienste und Kreditwürdigkeitsentscheidungen besonders streng; sobald HVOS in solche Entscheidungsbereiche hineinwächst, muss die Klassifizierung neu bewertet werden.

Der entscheidende Grundsatz lautet:

> **Gesetzestext ist keine Business Rule.**

Zwischen Rechtsquelle und ausführbarem Code liegt eine geprüfte Interpretation.

Diese Interpretation benötigt Version, Verantwortlichen und Gültigkeitszeitraum.

---

# 11 · Die neun Leitplanken

Die Leitplanken sollten so formuliert sein, dass sie tatsächlich Architekturentscheidungen erzwingen.

### 1. Kein Effekt ohne Mandat

Jede externe Wirkung benötigt eine explizite Authority Basis.

### 2. Kein Geld ohne Ledger

Finanzielle Zustände entstehen niemals ausschließlich aus Dokumenten oder Textinterpretationen.

### 3. Keine Berechnung ohne reproduzierbare Regel

Jeder geschäftskritische Wert muss erneut berechnet werden können.

### 4. Keine Behauptung ohne Evidenz

KI-Ausgaben bleiben Vorschläge, solange sie nicht an überprüfbare Quellen gebunden wurden.

### 5. Keine Gegenwartswahrheit ohne Zeitbezug

Verträge, Eigentum, Rollen, Schlüssel und Beschlüsse sind versioniert.

### 6. Keine Freigabe ohne verständliche Wirkung

Der Mensch genehmigt eine konkrete Zustandsänderung – keinen abstrakten KI-Vorschlag.

### 7. Keine Berechtigung durch das Modell

Modelle dürfen Policies nutzen, aber niemals verändern oder umgehen.

### 8. Reversibel standardmäßig, irreversibel explizit

Wo technisch möglich, werden Aktionen rückgängig oder kompensierbar gestaltet.

### 9. Unsicherheit stoppt Wirkung, nicht Arbeit

Bei Unsicherheit darf das System weiterhin recherchieren, strukturieren, simulieren und vorbereiten.

Es darf lediglich keine unzulässig sichere externe Wirkung erzeugen.

Das ist entscheidend.

**Fail safe** darf nicht bedeuten, dass das System bei jeder Unsicherheit handlungsunfähig wird.

---

# 12 · Bau-Reihenfolge

Auch die Reihenfolge sollte angepasst werden.

Der häufigste Fehler wäre, zuerst einen intelligenten Agenten zu bauen und anschließend Sicherheitsregeln darum herumzulegen.

HVOS sollte genau andersherum entstehen.

**Zuerst Wahrheit.**

Dann **Befugnis.**

Dann **Handlung.**

Erst danach **Intelligenz.**

Die sinnvolle Reihenfolge lautet deshalb sinngemäß:

**Domain-Modell → Ledger → Mandate & Rollen → Legal/Policy Registry → deterministische Fachlogik → Audit & Provenance → Action Contracts → Approval Engine → Integrationen → Intelligence Layer → Decision Experience → autonome Optimierung.**

Vor produktiver Autonomie kommt zusätzlich eine **Shadow-Phase**.

Das System bearbeitet reale oder historische Vorgänge, erzeugt Entscheidungen und Aktionen, führt diese jedoch nicht aus.

Anschließend wird verglichen:

Was hätte HVOS getan?

Was hat die Verwaltung tatsächlich getan?

Wo weichen Ergebnisse voneinander ab?

Welche Fehler wären teuer gewesen?

Welche Freigaben wären unnötig gewesen?

Erst nach diesem Replay darf eine Action Class schrittweise Produktionsrechte erhalten.

---

# 13 · Fehlendes Kapitel: Berechtigungs- und Sicherheitsmodell

Dieses Kapitel sollte ergänzt werden.

Ein KI-natives Hausverwaltungs-OS verwaltet Zugriff auf Geld, personenbezogene Daten, Verträge und Kommunikationskanäle.

Deshalb ist Security keine Infrastrukturfußnote.

HVOS benötigt mindestens ein Prinzip aus:

**Least Privilege + Mandantentrennung + kurzlebigen Credentials + nachvollziehbaren Service-Identitäten + getrennten Schreib- und Leserechten.**

Ein Modell erhält niemals pauschal:

„Zugriff auf Banking“.

Es erhält beispielsweise:

`propose_payment`

während eine gesonderte Ausführungsidentität ausschließlich nach erfolgreicher Policy-Prüfung

`execute_payment`

ausführen kann.

So wird ein kompromittierter Prompt nicht automatisch zu einem kompromittierten Bankkonto.

Auch Datenschutz durch Technikgestaltung und Datenminimierung müssen auf dieser Ebene umgesetzt werden.

---

# 14 · Fehlendes Kapitel: Failure & Incident Model

Ein System ist nicht sicher, weil es keine Fehler macht.

Es ist sicher, wenn Fehler **begrenzt, sichtbar und reparierbar** bleiben.

Für jede produktive Action Class muss daher definiert sein:

Was passiert bei Timeout?

Was passiert bei doppelter Ausführung?

Was passiert, wenn ein externer Dienst Erfolg meldet, HVOS aber keine Bestätigung speichert?

Was passiert bei teilweise ausgeführten Multi-Step-Aktionen?

Was passiert, wenn eine Quelle nachträglich korrigiert wird?

Was passiert, wenn die verwendete Policy falsch war?

Das System benötigt deshalb Konzepte wie:

**idempotency, retry policy, dead-letter state, compensation action, reconciliation und incident escalation.**

„Rollback“ allein reicht nicht.

Eine bereits versendete E-Mail kann nicht zurückgerollt werden.

Sie kann nur durch eine Folgeaktion kompensiert werden.

---

# 15 · Fehlendes Kapitel: Evaluation & Quality Gates

Ein KI-System darf nicht anhand des subjektiven Eindrucks „funktioniert ziemlich gut“ produktiv werden.

Jede KI-Fähigkeit benötigt messbare Qualitätsgrenzen.

Extraktion kann beispielsweise anhand strukturierter Ground-Truth-Dokumente getestet werden.

Action Planning anhand historischer Fälle.

Erklärungen anhand fachlicher Vollständigkeit.

Provenance anhand korrekter Quellenbindung.

Zusätzlich muss zwischen zwei Fehlerarten unterschieden werden:

**False Positive:** System handelt, obwohl es nicht sollte.

**False Negative:** System eskaliert, obwohl es sicher hätte handeln können.

Bei einer Zahlung ist der erste Fehler typischerweise wesentlich kritischer.

Bei einer Fristwarnung kann der zweite Fehler kritisch sein.

Die Optimierung darf deshalb nicht auf eine einzige globale „Accuracy“-Zahl reduziert werden.

Jede Action Class benötigt ihr eigenes Risikoprofil.

---

# 16 · Fehlendes Kapitel: Change Management

Die größte Gefahr entsteht langfristig möglicherweise nicht aus einem einzelnen Modellfehler.

Sie entsteht aus Veränderung.

Gesetze ändern sich.

Verträge ändern sich.

Beschlüsse ändern Umlagen.

Verwaltermandate werden erweitert.

Bankintegrationen verändern Schnittstellen.

Modelle werden ausgetauscht.

Deshalb darf keine dieser Änderungen still in Produktion gelangen.

HVOS benötigt versionierte:

**Policies, Rules, Prompts, Modelle, Action Contracts und Integrationen.**

Eine neue Version muss gegen historische Fälle replaybar sein.

Das System muss beantworten können:

> Was hätte Version 2.4 bei den letzten 10.000 Vorgängen anders gemacht als Version 2.3?

Erst damit wird KI-Betrieb zu Engineering statt Hoffnung.

---

# Schlussprinzip

Die wichtigste Designentscheidung von HVOS ist nicht das verwendete Sprachmodell.

Es ist die **Grenze zwischen Interpretation und Wirkung**.

Auf der einen Seite liegen:

Dokumente, Sprache, Unsicherheit, Vorschläge, Mustererkennung und Planung.

Auf der anderen Seite liegen:

Geld, Fristen, Verträge, Forderungen, Beschlüsse, Nachrichten und Rechtswirkung.

Zwischen beiden Seiten steht kein einfacher „Human-in-the-loop“.

Dort stehen:

**strukturierte Tatsachen → deterministische Regeln → Mandate → Policies → Action Contracts → Freigaben → Audit.**

Die KI darf innerhalb dieses Systems sehr mächtig sein.

Sie darf die Verwaltung lesen.

Sie darf sie strukturieren.

Sie darf Zusammenhänge erkennen.

Sie darf Arbeit vorbereiten.

Sie darf Entscheidungen erklären.

Sie darf Vorgänge planen.

Und innerhalb explizit delegierter Grenzen darf sie auch selbst handeln.

Aber sie darf niemals ihre eigenen Grenzen definieren.

Das ist die eigentliche Betriebsordnung.

**Nicht: KI macht alles.**

**Sondern: Das System weiß exakt, was es weiß, warum es etwas darf und welche Wirkung es erzeugen wird – bevor es handelt.**