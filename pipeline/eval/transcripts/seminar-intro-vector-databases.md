# Introduction to Vector Databases
- **Date:** 2026-05-02
- **Sources:** Mic

## Transcript

**[00:00:02] [You]** Alright, let's get started. Today I want to give a practical introduction to vector databases — why they exist, how they work under the hood, and when you'd actually reach for one instead of a regular database.

**[00:00:18] [You]** So the core problem is this: traditional databases are great at exact lookups. You give it an ID or an exact string match, and it finds the row. But a lot of modern applications need similarity search instead — find me things that are conceptually close to this thing, not identical to it.

**[00:00:36] [You]** The classic example is semantic search over documents. If I search for "how do I reset my password", I want results about account recovery even if they never use the word "reset". Keyword search misses that. Similarity search over embeddings catches it.

**[00:00:53] [You]** So how does this work? You take a piece of text, or an image, or audio, and you run it through an embedding model. That gives you back a vector — usually somewhere between three hundred and a few thousand floating point numbers — that represents the semantic content of that input.

**[00:01:12] [You]** The key property is that similar things end up close together in that vector space, and dissimilar things end up far apart. So "how do I reset my password" and "I forgot my login" would end up close together, even though they share almost no words.

**[00:01:28] [You]** Now, once you have these vectors, the naive approach is: store them all, and when a query comes in, compute the distance from the query vector to every single stored vector, and return the closest ones. That's called exact nearest neighbor search, and it works fine for small datasets.

**[00:01:47] [You]** But it doesn't scale. If you have ten million vectors, computing ten million distance calculations per query is too slow for anything interactive. This is where vector databases earn their keep.

**[00:02:00] [You]** They use approximate nearest neighbor algorithms — ANN for short. The most common family right now is HNSW, hierarchical navigable small world graphs. The idea is you build a graph structure where nearby vectors are connected, and you can navigate that graph to find approximate nearest neighbors in logarithmic time instead of linear time.

**[00:02:22] [You]** The tradeoff is you give up a guarantee of finding the exact nearest neighbors, in exchange for massive speed gains. In practice, well-tuned ANN indexes get you ninety-five to ninety-nine percent of the accuracy of exact search at a tiny fraction of the cost.

**[00:02:40] [You]** Let's talk about when you'd actually use one of these versus just adding a vector column to Postgres with an extension like pgvector. Honestly, for most applications under a few million vectors, pgvector or a similar extension is genuinely the right call. You get transactional guarantees, you don't add a new system to operate, and the performance is good enough.

**[00:03:02] [You]** Dedicated vector databases start to make sense past that scale, or when you need specific features — things like real-time filtering combined with vector search, multi-tenancy at scale, or very low single-digit-millisecond latency requirements.

**[00:03:18] [You]** One more thing worth flagging: embedding quality matters more than which vector database you pick. A mediocre embedding model with a great vector database will underperform a great embedding model with a mediocre database. Don't spend three weeks benchmarking vector databases before you've validated your embedding model actually captures the similarity relationships you care about.

**[00:03:40] [You]** Okay, that's the conceptual foundation. Next session we'll get hands-on and actually build a small semantic search system, so come with a laptop and Python set up. Any quick questions before we wrap up today?
