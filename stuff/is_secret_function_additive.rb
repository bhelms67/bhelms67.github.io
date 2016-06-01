#!/usr/bin/ruby

def secret(num)
  num
end

def is_prime?(num)
  (2..Math.sqrt(num).ceil).each do |divisor|
    if num%divisor == 0
      return false
    end
  end
end

def primes_array(limit)
  primes = Array.new
  primes.push(2)

  (2..limit).each do |num|
    if is_prime?(num)
      primes.push(num)
    end
  end

  primes
end

def is_additive?(n1, n2)
  secret(n1 + n2) == secret(n1) + secret(n2)
end

def is_function_additive?(num)
  primes = primes_array(num)

  primes.each do |n1|
    (primes.find_index(n1)..primes.length-1).each do |n2|
      return false unless is_additive?(n1, primes[n2])
    end
  end

  true
end

puts "Secret function #{is_function_additive?(Integer(ARGV[0])) ? 'is' : 'is not'} additive"
