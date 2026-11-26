// Choose the newest alert_queue_YYYY-MM-DD.csv in the inbox. Python reference: churn.as_of_from_name.
const NAME = /^alert_queue_([0-9]{4}-[0-9]{2}-[0-9]{2})\.csv$/;
const dated = $input.all()
  .map((item) => {
    const name = item.binary && item.binary.data ? item.binary.data.fileName : '';
    const match = NAME.exec(name || '');
    return match ? { item, asOf: match[1] } : null;
  })
  .filter(Boolean)
  .sort((a, b) => (a.asOf < b.asOf ? 1 : -1));
if (!dated.length) throw new Error('no alert_queue_YYYY-MM-DD.csv in the inbox; nothing was posted');
return [{ json: { asOf: dated[0].asOf }, binary: dated[0].item.binary }];
