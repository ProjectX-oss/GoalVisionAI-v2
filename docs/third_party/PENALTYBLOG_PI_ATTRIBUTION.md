# Penaltyblog Pi Ratings attribution

GoalVision AI's `app.lab_v2_shadow.pi_ratings` is an independent,
dependency-free implementation of the published Pi-rating update equations.
It follows the behavior documented by the `PiRatingSystem` API in penaltyblog,
copyright 2021 Martin Eastwood, which is distributed under the MIT License.

The implementation was written for GoalVision AI rather than copied verbatim.
It uses only completed football match identities, dates, teams and goal totals.
It neither accepts nor reads bookmaker odds.

References:

- Constantinou, A. C. and Fenton, N. E. (2012), *Solving the problem of
  inadequate scoring rules for assessing probabilistic football forecast
  models*.
- https://github.com/martineastwood/penaltyblog
- https://penaltyblog.readthedocs.io/en/latest/ratings/pi.html

License notice for the referenced penaltyblog implementation:

> Copyright 2021 Martin Eastwood
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to
> deal in the Software without restriction, including without limitation the
> rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
> sell copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the condition that the copyright and
> permission notice are included in copies or substantial portions.
>
> The software is provided "as is", without warranty of any kind.
