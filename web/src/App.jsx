import { useEffect, useState } from "react";
import { createFund, listFunds, updateFund } from "./api.js";

const EMPTY = { fund_name: "", strategy: "", vintage_year: "", commitment: "" };

export default function App() {
  const [funds, setFunds] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);

  const refresh = () => listFunds().then(setFunds).catch((e) => setError(e.message));
  useEffect(() => {
    refresh();
  }, []);

  const startEdit = (fund) => {
    setEditingId(fund.id);
    setForm({
      fund_name: fund.fund_name,
      strategy: fund.strategy,
      vintage_year: String(fund.vintage_year),
      commitment: fund.commitment,
    });
    setError(null);
  };

  const reset = () => {
    setEditingId(null);
    setForm(EMPTY);
    setError(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form, vintage_year: Number(form.vintage_year) };
    try {
      if (editingId === null) await createFund(payload);
      else await updateFund(editingId, payload);
      reset();
      refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const field = (name, label, props = {}) => (
    <label>
      {label}
      <input
        value={form[name]}
        onChange={(e) => setForm({ ...form, [name]: e.target.value })}
        required
        {...props}
      />
    </label>
  );

  return (
    <main>
      <h1>Funds</h1>

      <form onSubmit={submit}>
        <h2>{editingId === null ? "Add fund" : `Edit fund #${editingId}`}</h2>
        {field("fund_name", "Name")}
        {field("strategy", "Strategy")}
        {field("vintage_year", "Vintage", { type: "number" })}
        {field("commitment", "Commitment", { placeholder: "$1,200,000 USD" })}
        <div className="actions">
          <button type="submit">{editingId === null ? "Add" : "Save"}</button>
          {editingId !== null && (
            <button type="button" onClick={reset}>
              Cancel
            </button>
          )}
        </div>
        {error && <p className="error">{error}</p>}
      </form>

      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Strategy</th>
            <th>Vintage</th>
            <th className="num">Commitment</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {funds.map((f) => (
            <tr key={f.id} className={f.id === editingId ? "editing" : undefined}>
              <td>{f.id}</td>
              <td>{f.fund_name}</td>
              <td>{f.strategy}</td>
              <td>{f.vintage_year}</td>
              <td className="num">{f.commitment}</td>
              <td>
                <button onClick={() => startEdit(f)}>Edit</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
