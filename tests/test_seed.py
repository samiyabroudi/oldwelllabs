import pytest

from app import seed

HEADER = "id,fund_name,strategy,vintage_year,commitment\n"


def write_csv(tmp_path, monkeypatch, rows):
    path = tmp_path / "funds.csv"
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    monkeypatch.setattr(seed, "CSV_PATH", path)


def test_reads_and_normalizes_valid_rows(tmp_path, monkeypatch):
    write_csv(tmp_path, monkeypatch, ['7,Fund A,Buyout,2012," $1,000 USD "\n'])
    assert seed.read_csv() == [
        (7, {"fund_name": "Fund A", "strategy": "Buyout", "vintage_year": 2012, "commitment": "$1,000 USD"})
    ]


def test_every_row_of_the_real_csv_is_valid():
    assert len(seed.read_csv()) == 50


def test_reports_every_invalid_row_and_exits(tmp_path, monkeypatch):
    # read_csv runs before recreate_database in `make seed`, so exiting here leaves the
    # existing database untouched.
    write_csv(tmp_path, monkeypatch, [
        '1,Good,Buyout,2012,"$1 USD"\n',
        '2,Negative,Buyout,2012,"-$5,000 USD"\n',
        '3,Future,Buyout,99999,"$1 USD"\n',
        'x,Bad id,Buyout,2012,"$1 USD"\n',
    ])
    with pytest.raises(SystemExit) as exc:
        seed.read_csv()
    message = str(exc.value)
    assert "id='2': commitment='-$5,000 USD'" in message
    assert "id='3': vintage_year='99999'" in message
    assert "id='x'" in message
    assert "id='1'" not in message
